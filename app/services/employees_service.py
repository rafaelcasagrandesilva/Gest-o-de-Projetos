from __future__ import annotations

from datetime import date

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func, select

from app.core.scenario import Scenario
from app.models.company_finance import CompanyFinancialItem
from app.models.employee import Employee, EmployeeAllocation
from app.models.employee_assignment import EmployeeAssignment
from app.models.fleet import Vehicle
from app.models.payable_snapshot import PayableSnapshot, PayableSnapshotType
from app.models.project_operational import ProjectLabor
from app.models.user import User
from app.repositories.employees import EmployeeRepository
from app.schemas.employees import EmployeeRead, HourlyReferenceRead
from app.services.audit_service import AuditService
from app.services.employee_cost_service import calculate_clt_cost, calculate_pj_total_cost
from app.services.payable_snapshot_service import PayableSnapshotService
from app.services.settings_service import SettingsService
from app.services.utils import model_to_dict
from app.utils.date_utils import normalize_competencia
from app.utils.lifecycle import DELETE_WITH_MOVEMENT_MSG, normalize_lifecycle


def default_cost_reference() -> date:
    return date.today().replace(day=1)


_EMPLOYEE_PAYABLE_COST_FIELDS = frozenset(
    {
        "salary_base",
        "additional_costs",
        "pj_hours_per_month",
        "pj_additional_cost",
        "has_periculosidade",
        "has_adicional_dirigida",
        "extra_hours_50",
        "extra_hours_70",
        "extra_hours_100",
    }
)

_EMPLOYEE_PATCHABLE = frozenset(
    {
        "full_name",
        "email",
        "role_title",
        "employment_type",
        "pix_key_type",
        "pix_key",
        "salary_base",
        "additional_costs",
        "is_active",
        "has_periculosidade",
        "has_adicional_dirigida",
        "extra_hours_50",
        "extra_hours_70",
        "extra_hours_100",
        "pj_hours_per_month",
        "pj_additional_cost",
        "start_date",
        "end_date",
        "cost_center",
        "can_allocate_other_cost_centers",
    }
)


class EmployeesService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.employees = EmployeeRepository(session)
        self.audit = AuditService(session)

    async def _compute_and_assign_total_cost(self, emp: Employee, *, reference: date | None) -> None:
        ref = reference or default_cost_reference()
        settings = await SettingsService(self.session).get_or_create()
        if emp.employment_type == "CLT":
            emp.total_cost = calculate_clt_cost(emp, settings, ref.year, ref.month)
        else:
            emp.total_cost = calculate_pj_total_cost(emp)

    async def active_assignment_cost_centers(self, employee_ids: list) -> dict:
        """Centros de Custo das alocações ATIVAS, por colaborador (uma query, sem N+1)."""
        ids = [i for i in employee_ids if i is not None]
        if not ids:
            return {}
        from app.models.employee_assignment import AssignmentStatus, EmployeeAssignment

        rows = (
            await self.session.execute(
                select(EmployeeAssignment.employee_id, EmployeeAssignment.cost_center).where(
                    EmployeeAssignment.employee_id.in_(ids),
                    EmployeeAssignment.status == AssignmentStatus.ATIVA,
                )
            )
        ).all()
        out: dict = {}
        for emp_id, cc in rows:
            nome = (cc or "").strip()
            if nome:
                out.setdefault(emp_id, set()).add(nome)
        return out

    #: 8h × 22 dias — base do salário de REFERÊNCIA de quem recebe por hora.
    REFERENCE_HOURS_PER_MONTH = 8 * 22

    async def hourly_references(self, employees: list) -> dict:
        """Salário de referência (valor-hora × 176h) de quem recebe por hora, por colaborador.

        Só EXIBIÇÃO na relação de colaboradores (pedido da diretoria: "quanto seria o salário").
        Não grava nada e não alimenta custo algum — Mão de Obra, Contas a Pagar e folha seguem
        vindo do que o gestor lança no projeto.

        Fonte do valor-hora: as alocações ATIVAS com horas definidas (uma linha por contrato);
        na falta, o cadastro PJ com horas/mês (ali `salary_base` já é valor-hora).
        """
        ids = [e.id for e in employees if e is not None and e.id is not None]
        if not ids:
            return {}
        from app.models.employee_assignment import AssignmentStatus, EmployeeAssignment
        from app.models.project import Project

        horas = float(self.REFERENCE_HOURS_PER_MONTH)
        out: dict = {}
        rows = (
            await self.session.execute(
                select(
                    EmployeeAssignment.employee_id,
                    EmployeeAssignment.salary_base,
                    EmployeeAssignment.cost_center,
                    Project.name,
                )
                .outerjoin(Project, Project.id == EmployeeAssignment.project_id)
                .where(
                    EmployeeAssignment.employee_id.in_(ids),
                    EmployeeAssignment.status == AssignmentStatus.ATIVA,
                    EmployeeAssignment.hours_per_month.is_not(None),
                    EmployeeAssignment.salary_base.is_not(None),
                )
                .order_by(EmployeeAssignment.created_at)
            )
        ).all()
        for emp_id, valor_hora, cc, projeto in rows:
            v = float(valor_hora)
            if v <= 0:
                continue
            out.setdefault(emp_id, []).append(
                {
                    "hourly_rate": v,
                    "reference_hours": horas,
                    "monthly_reference": round(v * horas, 2),
                    "cost_center": (cc or "").strip() or None,
                    "project_name": (projeto or "").strip() or None,
                }
            )
        for emp in employees:
            if emp.id in out or emp.employment_type != "PJ":
                continue
            if emp.salary_base and emp.pj_hours_per_month and float(emp.pj_hours_per_month) > 0:
                v = float(emp.salary_base)
                out[emp.id] = [
                    {
                        "hourly_rate": v,
                        "reference_hours": horas,
                        "monthly_reference": round(v * horas, 2),
                        "cost_center": None,
                        "project_name": None,
                    }
                ]
        return out

    async def labor_kinds(self, employee_ids: list, *, competencia: date) -> dict:
        """Mão de obra DIRETA/INDIRETA de cada colaborador na competência (derivada; três queries).

        DIRETA: tem Mão de Obra REALIZADA em projeto no mês (a mesma base do custo dos projetos)
        ou alocação ATIVA em projeto — assim a etiqueta não some no mês cuja Mão de Obra ainda
        não foi lançada.
        INDIRETA: está vinculado a um item dos Custos Indiretos (tipo custo_fixo) vigente no mês,
        pela MESMA regra de elegibilidade da geração do Contas a Pagar (sem regra paralela).
        Os dois → DIRETA_E_INDIRETA, que é legítimo quando a pessoa divide o tempo (ex.: 50% em
        projetos + 50% administrativo). `labor_over_allocated` só acende quando a soma conhecida
        passa de 100% — aí sim o custo está sendo contado em dobro.

        Retorna {employee_id: {"labor_kind": ..., "labor_over_allocated": bool}} (só classificados).
        """
        ids = [i for i in employee_ids if i is not None]
        if not ids:
            return {}
        from app.models.employee_assignment import AssignmentStatus

        comp = normalize_competencia(competencia)
        pct_projeto = {
            emp_id: float(pct or 0)
            for emp_id, pct in (
                await self.session.execute(
                    select(ProjectLabor.employee_id, func.sum(ProjectLabor.allocation_percentage))
                    .where(
                        ProjectLabor.employee_id.in_(ids),
                        ProjectLabor.competencia == comp,
                        ProjectLabor.scenario == Scenario.REALIZADO,
                        ProjectLabor.allocation_percentage > 0,
                    )
                    .group_by(ProjectLabor.employee_id)
                )
            ).all()
        }
        alocados = set(
            (
                await self.session.execute(
                    select(EmployeeAssignment.employee_id)
                    .where(
                        EmployeeAssignment.employee_id.in_(ids),
                        EmployeeAssignment.status == AssignmentStatus.ATIVA,
                        EmployeeAssignment.project_id.is_not(None),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        itens = (
            (
                await self.session.execute(
                    select(CompanyFinancialItem).where(
                        CompanyFinancialItem.tipo == "custo_fixo",
                        CompanyFinancialItem.employee_id.in_(ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        elegivel = PayableSnapshotService(self.session)._company_finance_item_eligible_for_comp
        # Percentual indireto por colaborador; None = item sem percentual (soma desconhecida).
        pct_indireto: dict = {}
        for it in itens:
            if not elegivel(it, comp):
                continue
            atual = pct_indireto.get(it.employee_id, 0.0)
            pct = float(it.percentual) if it.percentual is not None else None
            pct_indireto[it.employee_id] = None if atual is None or pct is None else atual + pct
        out: dict = {}
        for emp_id in ids:
            direta = emp_id in pct_projeto or emp_id in alocados
            indireta = emp_id in pct_indireto
            if not (direta or indireta):
                continue
            kind = "DIRETA_E_INDIRETA" if direta and indireta else ("DIRETA" if direta else "INDIRETA")
            soma_conhecida = indireta and emp_id in pct_projeto and pct_indireto[emp_id] is not None
            out[emp_id] = {
                "labor_kind": kind,
                "labor_over_allocated": bool(
                    soma_conhecida and pct_projeto[emp_id] + pct_indireto[emp_id] > 100.0 + 1e-6
                ),
            }
        return out

    @staticmethod
    def _merge_cost_centers(principal: str | None, alocados: set | None) -> list[str]:
        """Centro do cadastro + centros das alocações, sem repetir, em ordem estável."""
        nomes = []
        vistos = set()
        for nome in [(principal or "").strip(), *sorted(alocados or ())]:
            chave = nome.lower()
            if nome and chave not in vistos:
                vistos.add(chave)
                nomes.append(nome)
        return nomes

    async def employee_to_read(self, emp: Employee, *, competencia: date) -> EmployeeRead:
        settings = await SettingsService(self.session).get_or_create()
        if emp.employment_type == "CLT":
            tc = calculate_clt_cost(emp, settings, competencia.year, competencia.month)
        else:
            tc = calculate_pj_total_cost(emp)
        alocados = (await self.active_assignment_cost_centers([emp.id])).get(emp.id)
        kinds = await self.labor_kinds([emp.id], competencia=competencia)
        referencias = (await self.hourly_references([emp])).get(emp.id, [])
        base = EmployeeRead.model_validate(emp)
        return base.model_copy(
            update={
                "total_cost": tc,
                "cost_centers": self._merge_cost_centers(emp.cost_center, alocados),
                "hourly_reference": [HourlyReferenceRead(**r) for r in referencias],
                **kinds.get(emp.id, {}),
            }
        )

    async def list_employees_as_read(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        competencia: date,
        search: str | None = None,
        cost_center: str | None = None,
        strict_cost_center: bool = False,
    ) -> list[EmployeeRead]:
        # Filtro por Centro de Custo é TEMPORAL: resolve pela própria `competencia` do
        # relatório/lista (histórico). O valor congelado no cache não governa mais.
        rows = await self.employees.list(
            offset=offset,
            limit=limit,
            search=search,
            cost_center=cost_center,
            competence=competencia,
            strict_cost_center=strict_cost_center,
        )
        settings = await SettingsService(self.session).get_or_create()
        y, m = competencia.year, competencia.month
        centros = await self.active_assignment_cost_centers([e.id for e in rows])
        kinds = await self.labor_kinds([e.id for e in rows], competencia=competencia)
        referencias = await self.hourly_references(rows)
        out: list[EmployeeRead] = []
        for emp in rows:
            if emp.employment_type == "CLT":
                tc = calculate_clt_cost(emp, settings, y, m)
            else:
                tc = calculate_pj_total_cost(emp)
            out.append(
                EmployeeRead.model_validate(emp).model_copy(
                    update={
                        "total_cost": tc,
                        "cost_centers": self._merge_cost_centers(emp.cost_center, centros.get(emp.id)),
                        "hourly_reference": [
                            HourlyReferenceRead(**r) for r in referencias.get(emp.id, [])
                        ],
                        **kinds.get(emp.id, {}),
                    }
                )
            )
        return out

    async def list_employees(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        cost_center: str | None = None,
        competence: date | None = None,
    ) -> list[Employee]:
        return await self.employees.list(
            offset=offset, limit=limit, search=search, cost_center=cost_center, competence=competence
        )

    async def cost_center_for_project(self, project_id) -> str | None:
        """Centro de Custo efetivo do projeto (para filtrar colaboradores elegíveis).

        Usa `projects.cost_center` quando preenchido; caso contrário cai para o NOME do
        projeto — que é o agrupamento de fato hoje (a coluna cost_center dos projetos
        ainda não é populada). Assim o filtro já funciona com os dados atuais e passa a
        respeitar o cost_center explícito assim que ele for cadastrado.
        """
        from app.models.project import Project

        proj = await self.session.get(Project, project_id)
        if proj is None:
            return None
        cc = (getattr(proj, "cost_center", None) or "").strip()
        if cc:
            return cc
        name = (getattr(proj, "name", None) or "").strip()
        return name or None

    async def cost_center_filter_for_project(self, project_id) -> str | None:
        """Centro de Custo a aplicar no filtro de Mão de Obra.

        PONTO ÚNICO de resolução, reutilizado por TODOS os endpoints de listagem de
        colaboradores (evita regra duplicada): com projeto → Centro de Custo do projeto;
        sem projeto → None (sem filtro). O WHERE em si vive só no repositório
        (`EmployeeRepository.list`).
        """
        if project_id is None:
            return None
        return await self.cost_center_for_project(project_id)

    async def list_employees_for_project(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        project_id=None,
        competence: date | None = None,
    ) -> list[Employee]:
        """Lista colaboradores já filtrados pelo Centro de Custo do projeto (Mão de Obra).

        Com `competence`, a elegibilidade respeita o Centro de Custo VIGENTE na competência
        (histórico). Sem ela, usa o cache (compatibilidade).
        """
        cc = await self.cost_center_filter_for_project(project_id)
        return await self.list_employees(
            offset=offset, limit=limit, search=search, cost_center=cc, competence=competence
        )

    async def list_employees_read_for_project(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        competencia: date,
        search: str | None = None,
        project_id=None,
        strict_cost_center: bool = False,
    ) -> list[EmployeeRead]:
        """Idem `list_employees_for_project`, porém já no formato de leitura (com custo).

        `strict_cost_center` serve à RELAÇÃO de colaboradores (tela Colaboradores): traz só quem
        é do centro do projeto ou tem alocação ativa nele. O padrão (False) preserva o seletor de
        Mão de Obra, onde quem não tem centro precisa continuar disponível para ser alocado.
        """
        cc = await self.cost_center_filter_for_project(project_id)
        return await self.list_employees_as_read(
            offset=offset,
            limit=limit,
            competencia=competencia,
            search=search,
            cost_center=cc,
            strict_cost_center=strict_cost_center,
        )

    async def get_employee(self, employee_id) -> Employee:
        emp = await self.employees.get(employee_id)
        if not emp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colaborador não encontrado.")
        return emp

    async def create_employee(
        self,
        *,
        actor_user_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> Employee:
        payload = {**data}
        payload.pop("total_cost", None)
        ref = payload.pop("cost_reference_competencia", None)
        ref_date = ref if isinstance(ref, date) else default_cost_reference()

        employment_type = payload.get("employment_type") or "CLT"
        if employment_type == "CLT":
            sb = payload.get("salary_base")
            if sb is not None and float(sb) < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Salário base não pode ser negativo.",
                )

        is_active = bool(payload.get("is_active", True))
        try:
            end_date = normalize_lifecycle(is_active=is_active, end_date=payload.get("end_date"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        emp = Employee(
            full_name=payload["full_name"],
            email=payload.get("email"),
            role_title=payload.get("role_title"),
            employment_type=employment_type,
            salary_base=payload.get("salary_base"),
            additional_costs=payload.get("additional_costs"),
            is_active=is_active,
            start_date=payload.get("start_date"),
            end_date=end_date,
            cost_center=(str(payload["cost_center"]).strip() if payload.get("cost_center") else None),
            can_allocate_other_cost_centers=bool(payload.get("can_allocate_other_cost_centers", False)),
            has_periculosidade=bool(payload.get("has_periculosidade", False)),
            has_adicional_dirigida=bool(payload.get("has_adicional_dirigida", False)),
            extra_hours_50=float(payload.get("extra_hours_50") or 0),
            extra_hours_70=float(payload.get("extra_hours_70") or 0),
            extra_hours_100=float(payload.get("extra_hours_100") or 0),
            pj_hours_per_month=payload.get("pj_hours_per_month"),
            pj_additional_cost=float(payload.get("pj_additional_cost") or 0),
        )
        await self._compute_and_assign_total_cost(emp, reference=ref_date)
        await self.employees.add(emp)
        # Histórico inicial do Centro de Custo (fonte da verdade temporal).
        from app.services.cost_center_history_service import EmployeeCostCenterService

        await EmployeeCostCenterService(self.session).ensure_initial_history(emp)
        await self.audit.log_action(
            user=actor,
            action="create",
            entity="employee",
            entity_id=emp.id,
            before=None,
            after=model_to_dict(emp),
            context={"employee_name": emp.full_name, "descricao": "Cadastro de colaborador"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(emp)
        return emp

    async def update_employee(
        self,
        *,
        actor_user_id,
        employee_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> Employee:
        emp = await self.get_employee(employee_id)
        before = model_to_dict(emp)
        data.pop("total_cost", None)
        ref = data.pop("cost_reference_competencia", None)
        ref_date = ref if isinstance(ref, date) else None
        # Centro de Custo é TEMPORAL: não setar direto o cache; roteia pelo histórico
        # (fecha a linha anterior, abre nova a partir da competência informada).
        cc_touched = "cost_center" in data
        new_cc = data.pop("cost_center", None)
        cc_effective = data.pop("cost_center_effective_date", None)
        patch = {k: v for k, v in data.items() if k in _EMPLOYEE_PATCHABLE}
        for k, v in patch.items():
            setattr(emp, k, v)
        if cc_touched:
            from app.services.cost_center_history_service import EmployeeCostCenterService

            await EmployeeCostCenterService(self.session).change_cost_center(
                emp, new_cc, cc_effective if isinstance(cc_effective, date) else default_cost_reference()
            )

        # Invariante do ciclo de vida (apenas quando o status/encerramento é tocado, para
        # não bloquear edições não relacionadas): inativo exige end_date; ativo limpa-o.
        if "is_active" in patch or "end_date" in patch:
            try:
                emp.end_date = normalize_lifecycle(is_active=bool(emp.is_active), end_date=emp.end_date)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        if emp.employment_type == "CLT":
            sb = emp.salary_base
            if sb is None or float(sb) <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Colaborador CLT exige salário base maior que zero.",
                )

        await self._compute_and_assign_total_cost(emp, reference=ref_date)
        if _EMPLOYEE_PAYABLE_COST_FIELDS & patch.keys():
            await PayableSnapshotService(self.session).sync_collaborator_payables_for_employee(
                employee_id=emp.id
            )
        await self.audit.log_action(
            user=actor,
            action="update",
            entity="employee",
            entity_id=emp.id,
            before=before,
            after=model_to_dict(emp),
            context={"employee_name": emp.full_name, "descricao": "Atualização de colaborador"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(emp)
        return emp

    async def _has_movement(self, employee_id) -> bool:
        """True se o colaborador possui movimentação vinculada (impede exclusão física).

        Considera: FOLHA por competência (`project_labors`), títulos de Mão de obra já
        gerados no Contas a Pagar, ALOCAÇÕES (`employee_assignments`), itens de custo-matriz
        (COLABORADOR_MATRIZ) e vínculo como motorista de veículo. Basta uma referência para
        preservar o histórico — o caminho correto nesses casos é INATIVAR o cadastro.

        `employee_allocations` continua na lista só por compatibilidade: a tabela em uso é
        `employee_assignments` (a seção "Alocações" da tela). A antiga estava vazia, então
        a checagem existia mas nunca podia barrar nada.

        `project_labors` é o item mais importante desta lista e faltava. A FK
        `project_labors.employee_id` é ON DELETE CASCADE: sem esta checagem, excluir o
        cadastro apagava silenciosamente todas as competências de folha do colaborador —
        e, com elas, a origem dos títulos do Contas a Pagar, que passavam a acusar
        "resíduo" na reconciliação sem que ninguém tivesse mexido no projeto.
        """
        for stmt in (
            select(func.count()).select_from(ProjectLabor).where(
                ProjectLabor.employee_id == employee_id
            ),
            select(func.count()).select_from(PayableSnapshot).where(
                PayableSnapshot.ref_id == employee_id,
                PayableSnapshot.type == PayableSnapshotType.COLLABORATOR,
            ),
            select(func.count()).select_from(EmployeeAssignment).where(
                EmployeeAssignment.employee_id == employee_id
            ),
            select(func.count()).select_from(EmployeeAllocation).where(
                EmployeeAllocation.employee_id == employee_id
            ),
            select(func.count()).select_from(CompanyFinancialItem).where(
                CompanyFinancialItem.employee_id == employee_id
            ),
            select(func.count()).select_from(Vehicle).where(Vehicle.driver_employee_id == employee_id),
        ):
            if int((await self.session.execute(stmt)).scalar_one() or 0) > 0:
                return True
        return False

    async def delete_employee(
        self,
        *,
        actor_user_id,
        employee_id,
        actor: User | None = None,
        request: Request | None = None,
    ) -> None:
        emp = await self.get_employee(employee_id)
        if await self._has_movement(employee_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=DELETE_WITH_MOVEMENT_MSG)
        before = model_to_dict(emp)
        await self.employees.delete(emp)
        await self.audit.log_action(
            user=actor,
            action="delete",
            entity="employee",
            entity_id=employee_id,
            before=before,
            after=None,
            context={
                "employee_name": before.get("full_name"),
                "descricao": "Exclusão de colaborador",
            },
            request=request,
        )
        await self.session.commit()

    # Os métodos do vínculo percentual legado (`EmployeeAllocation`) foram removidos na limpeza
    # da RC junto com seus endpoints: 0 linhas na tabela, nenhum consumidor. Colaborador × projeto
    # é `ProjectLabor`; o contrato é `EmployeeAssignment`.
