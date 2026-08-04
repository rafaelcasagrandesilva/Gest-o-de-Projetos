from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.schemas.dashboard import DirectorSummary, FinancialDashboardSummary, MonthlyPoint
from app.services.company_finance_service import CompanyFinanceService
from app.services.dashboard_service import DashboardService
from app.services.employees_service import default_cost_reference
from app.services.fleet_service import FleetService, fleet_vehicle_to_read
from app.services.project_structure_service import ProjectStructureService
from app.services.projects_service import ProjectsService
from app.services.financial_crud_service import FinancialCrudService
from app.services.payroll_service import PayrollService
from app.services.receivable_service import ReceivableService
from app.services.users_service import UsersService
from app.core.scenario import DEFAULT_SCENARIO, Scenario, coerce_scenario
from app.utils.date_utils import (
    iter_competencias_inclusive,
    next_competencia,
    normalize_competencia,
    period_last_n_months,
)

logger = logging.getLogger(__name__)


def _uuid(filters: dict[str, Any], key: str) -> UUID | None:
    raw = filters.get(key)
    if raw is None or raw == "":
        return None
    if isinstance(raw, UUID):
        return raw
    return UUID(str(raw))


def _competencia_date(filters: dict[str, Any], key: str = "competencia") -> date | None:
    raw = filters.get(key)
    if raw is None or raw == "":
        return None
    if isinstance(raw, date):
        return normalize_competencia(raw)
    s = str(raw).strip()
    if len(s) >= 10 and s[4] == "-":
        y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
        return date(y, m, d)
    if len(s) == 7 and s[4] == "-":
        y, m = int(s[0:4]), int(s[5:7])
        return date(y, m, 1)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} inválido (use YYYY-MM).")


def _payroll_distribution_label(line: Any) -> str:
    """Coluna "Projetos / Administrativo": como o colaborador está distribuído.

    Ex.: "Fiscalização AT (100%)"; "Fiscalização AT (50%) / Administrativo (50%)";
    "Administrativo"; "—" (sem alocação)."""
    if line is None:
        return "—"
    slices = list(getattr(line, "by_project", None) or [])
    parts: list[str] = []
    total_pct = 0.0
    for s in slices:
        pct = float(getattr(s, "allocation_percentage", 0) or 0)
        total_pct += pct
        parts.append(f"{getattr(s, 'project_name', '')} ({pct:.0f}%)")
    remainder = round(100.0 - total_pct, 2)
    if parts:
        if remainder > 0.5:
            parts.append(f"Administrativo ({remainder:.0f}%)")
        return " / ".join(parts)
    if float(getattr(line, "administrative_cost", 0) or 0) > 0:
        return "Administrativo"
    return "—"


def _payroll_component_label_from_name(name: str, *, fallback: str) -> str:
    """Rótulo da COLUNA de componente a partir do nome do snapshot do CAP.

    A geração grava o nome como "<Colaborador> — <Componente>" (ou só "<Colaborador>"
    para a linha única). O sufixo após o último " — " é o componente. Isto é apenas
    ROTULAÇÃO de coluna — a atribuição ao colaborador é 100% estrutural (ref_id); um nome
    fora do padrão apenas cai na coluna de fallback, sem afetar valor nem total.
    """
    raw = (name or "").strip()
    if " — " in raw:
        suffix = raw.rsplit(" — ", 1)[1].strip()
        if suffix:
            return suffix
    return fallback


def _payroll_distribution_from_snapshots(pairs: list[tuple[str, float]]) -> str:
    """Distribuição por Centro de Custo derivada dos próprios lançamentos do CAP (por valor).

    Ex.: "Subterrâneo (71%) / Fiscalização AT (29%)". Substitui a antiga derivação via
    build_payroll — agora reflete exatamente onde o CAP distribui a folha do colaborador.
    """
    agg: dict[str, float] = {}
    total = 0.0
    for cc, val in pairs:
        key = (cc or "").strip() or "—"
        agg[key] = agg.get(key, 0.0) + float(val or 0)
        total += float(val or 0)
    if not agg or total <= 0:
        return "—"
    parts = [
        f"{cc} ({round(v / total * 100):.0f}%)"
        for cc, v in sorted(agg.items(), key=lambda kv: -kv[1])
    ]
    return " / ".join(parts)


def _payroll_cost_center_distribution(line: Any, proj_cc: dict) -> str:
    """Distribuição do colaborador por Centro de Custo (agrega % de alocação por centro
    dos projetos). Ex.: "Subterrâneo (70%) / Administrativo (30%)". Preserva a informação
    de distribuição que antes ficava na coluna principal (agora "Centro de Custo")."""
    if line is None:
        return "—"
    agg: dict[str, float] = {}
    total_pct = 0.0
    for s in list(getattr(line, "by_project", None) or []):
        pct = float(getattr(s, "allocation_percentage", 0) or 0)
        total_pct += pct
        cc = (proj_cc.get(getattr(s, "project_id", None)) or "").strip() or (
            getattr(s, "project_name", "") or "—"
        )
        agg[cc] = agg.get(cc, 0.0) + pct
    remainder = round(100.0 - total_pct, 2)
    if remainder > 0.5:
        agg["Administrativo"] = agg.get("Administrativo", 0.0) + remainder
    if not agg:
        return "Administrativo" if float(getattr(line, "administrative_cost", 0) or 0) > 0 else "—"
    parts = [f"{cc} ({pct:.0f}%)" for cc, pct in sorted(agg.items(), key=lambda kv: -kv[1])]
    return " / ".join(parts)


class ReportService:
    """Monta dados estruturados para relatórios (sem renderização)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_project_summary(
        self, *, project_id: UUID, competencia: date, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> dict[str, Any]:
        sc = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        proj = await self.session.get(Project, project_id)
        if not proj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
        dash = DashboardService(self.session)
        pst = ProjectStructureService(self.session)
        summary = await dash.resumo_por_projeto(project_id=project_id, competencia=comp, scenario=sc)
        labor = await pst.list_labor_details(project_id=project_id, competencia=comp, scenario=sc)
        vehicles = await pst.list_project_vehicles_read(project_id=project_id, competencia=comp, scenario=sc)
        systems = await pst.list_systems(project_id=project_id, competencia=comp, scenario=sc)
        fixed = await pst.list_fixed(project_id=project_id, competencia=comp, scenario=sc)
        return {
            "project_name": proj.name,
            "competencia": comp.isoformat(),
            "scenario": sc.value,
            "summary": summary,
            "labor": [x.model_dump(mode="json") for x in labor],
            "vehicles": [x.model_dump(mode="json") for x in vehicles],
            "systems": [
                {"id": str(x.id), "name": x.name, "value": float(x.value)} for x in systems
            ],
            "fixed_operational": [
                {"id": str(x.id), "name": x.name, "value": float(x.value)} for x in fixed
            ],
        }

    async def generate_company_summary(
        self, *, competencia: date, project_ids: list[UUID], scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> dict[str, Any]:
        sc = coerce_scenario(scenario)
        comp = normalize_competencia(competencia)
        dash = DashboardService(self.session)
        rows = await dash.list_projects_financial_summaries(
            competencia=comp, project_ids=project_ids, scenario=sc
        )
        return {"competencia": comp.isoformat()[:7], "scenario": sc.value, "rows": rows}

    # Chaves financeiras dos relatórios de Colaboradores/Folha — omitidas sem employees.sensitive.
    _EMPLOYEES_REPORT_SENSITIVE_KEYS = (
        "salario_base", "custos_adicionais", "custo_total_cadastro", "pj_horas_mes",
        "pj_custo_adicional", "custo_projetos", "custo_administrativo", "custo",
        "pix_tipo", "pix_chave",
    )
    # Chaves FIXAS sensíveis do relatório de folha. Os componentes da remuneração NÃO
    # entram aqui: vivem em `row["componentes"]` (colunas dinâmicas) e são redigidos em
    # bloco, para que um componente novo nasça protegido em vez de vazar por omissão.
    _PAYROLL_REPORT_SENSITIVE_KEYS = (
        "endividamentos", "endividamentos_itens", "total_folha", "pix_tipo", "pix_chave",
    )

    async def generate_employees_report(
        self,
        *,
        competencia: date | None,
        scenario: str | Scenario = DEFAULT_SCENARIO,
        include_sensitive: bool = True,
    ) -> dict[str, Any]:
        comp = competencia or default_cost_reference()
        sc = coerce_scenario(scenario)
        payroll = await PayrollService(self.session).build_payroll(
            competencia=comp, scenario=sc, project_id=None
        )

        # Junta o custo de folha (por competência) com o CADASTRO do colaborador.
        from sqlalchemy import select as _select
        from app.models.employee import Employee

        emps = (await self.session.execute(_select(Employee))).scalars().all()
        emp_by_id = {e.id: e for e in emps}
        # Centros de custo dos projetos alocados (para a coluna de relacionamentos).
        proj_ids = {
            s.project_id for line in payroll.lines for s in (line.by_project or []) if s.project_id
        }
        proj_cc: dict[UUID, str] = {}
        if proj_ids:
            prows = (await self.session.execute(_select(Project).where(Project.id.in_(proj_ids)))).scalars().all()
            proj_cc = {p.id: (p.cost_center or "") for p in prows}

        rows: list[dict[str, Any]] = []
        for line in payroll.lines:
            emp = emp_by_id.get(line.employee_id)
            slices = line.by_project or []
            projetos = "; ".join(
                f"{s.project_name} ({float(s.allocation_percentage):.0f}%)" for s in slices
            )
            ccs = sorted({proj_cc.get(s.project_id, "") for s in slices if proj_cc.get(s.project_id)})
            rows.append(
                {
                    # Identificação
                    "nome": line.full_name,
                    "email": (emp.email if emp else "") or "",
                    "cargo": line.role_title or "",
                    "tipo": line.employment_type,
                    "status": "Ativo" if line.is_active else "Inativo",
                    # Relacionamentos
                    "projetos": projetos,
                    "centros_custo": "; ".join(ccs),
                    # Valores (cadastro)
                    "salario_base": float(emp.salary_base) if (emp and emp.salary_base is not None) else "",
                    "custos_adicionais": float(emp.additional_costs) if (emp and emp.additional_costs is not None) else "",
                    "custo_total_cadastro": float(emp.total_cost) if emp else "",
                    "pj_horas_mes": float(emp.pj_hours_per_month) if (emp and emp.pj_hours_per_month is not None) else "",
                    "pj_custo_adicional": float(emp.pj_additional_cost) if emp else "",
                    # Adicionais
                    "periculosidade": ("Sim" if emp.has_periculosidade else "Não") if emp else "",
                    "adicional_dirigida": ("Sim" if emp.has_adicional_dirigida else "Não") if emp else "",
                    # Pagamento
                    "pix_tipo": (emp.pix_key_type if emp else "") or "",
                    "pix_chave": (emp.pix_key if emp else "") or "",
                    # Valores (folha na competência)
                    "custo_projetos": float(line.projects_total),
                    "custo_administrativo": float(line.administrative_cost),
                    "custo": float(line.grand_total),
                    # Datas
                    "criado_em": emp.created_at.isoformat() if (emp and getattr(emp, "created_at", None)) else "",
                    "atualizado_em": emp.updated_at.isoformat() if (emp and getattr(emp, "updated_at", None)) else "",
                }
            )
        if not include_sensitive:
            rows = [
                {k: ("" if k in self._EMPLOYEES_REPORT_SENSITIVE_KEYS else v) for k, v in row.items()}
                for row in rows
            ]
        return {"competencia_ref": comp.isoformat(), "scenario": sc.value, "rows": rows}

    async def generate_payroll_report(
        self,
        *,
        competencia: date | None,
        scenario: str | Scenario = DEFAULT_SCENARIO,
        include_sensitive: bool = True,
    ) -> dict[str, Any]:
        """Folha de Pagamento (fechamento mensal): consolidação FIEL dos lançamentos do
        Contas a Pagar referentes ao colaborador — é o documento enviado à consultoria de
        folha, portanto deve refletir EXATAMENTE o que será pago.

        Regra de negócio (definitiva): o relatório NÃO reconstrói valores, NÃO acrescenta
        folha não-alocada e NÃO usa o cadastro. Ele agrupa os snapshots do Contas a Pagar
        (`payable_snapshots`) do mês de pagamento, por colaborador. A classificação do que
        é folha usa a MESMA regra da tela do CAP (`app/services/payable_display.py`), sem
        heurística de nome:
          - FOLHA: linhas exibidas como "Colaborador" (type COLLABORATOR ou FIXED_COST com
            categoria "Colaborador");
          - Endividamento: linhas exibidas como "Endividamento" (vinculadas ao colaborador).
        A atribuição da linha ao colaborador é ESTRUTURAL (ref_id → employee, direto para
        COLLABORATOR e via CompanyFinancialItem.employee_id para os demais). MANUAL e demais
        categorias ficam de fora — exatamente como na tela.

        Invariante: Σ(relatório) = Σ(CAP referente ao colaborador), por CONSTRUÇÃO. Um novo
        tipo de folha aparece automaticamente nos dois lugares (regra compartilhada).

        Competência = mês TRABALHADO (rótulo); os pagamentos ocorrem no CAP do mês seguinte
        (`payment_month`), que é o mês efetivamente lido.
        """
        from sqlalchemy import select as _select
        from app.models.employee import Employee
        from app.models.company_finance import CompanyFinancialItem
        from app.models.payable_snapshot import PayableOrigin, PayableSnapshot, PayableSnapshotType
        from app.models.payment_component import PaymentVariableComponent
        from app.services.employee_cost_service import PAYROLL_COMPONENT_FALLBACK_LABEL
        from app.services.payable_display import is_collaborator_payroll, is_employee_debt

        comp = normalize_competencia(competencia or default_cost_reference())
        sc = coerce_scenario(scenario)
        comp_str = f"{comp.year:04d}-{comp.month:02d}"
        payment_month = next_competencia(comp)

        # 1) TODOS os lançamentos NÃO obsoletos do mês de pagamento (o que será pago).
        snaps = list(
            (
                await self.session.execute(
                    _select(PayableSnapshot).where(
                        PayableSnapshot.month == payment_month,
                        PayableSnapshot.is_obsolete.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )

        # 2) Resolução ESTRUTURAL do colaborador de cada lançamento (sem heurística de nome):
        #    - Componente Variável (origin=VARIABLE) → ref_id é payment_variable_components.id
        #      (vale para projeto E custo fixo); resolve o employee pelo componente;
        #    - COLLABORATOR → ref_id é o próprio Employee.id;
        #    - FIXED_COST/ENDIVIDAMENTO/FINANCIAL → ref_id é um CompanyFinancialItem cujo
        #      employee_id aponta o colaborador (quando vinculado).
        variable_ref_ids = {
            s.ref_id for s in snaps if s.ref_id is not None and (s.origin or "") == PayableOrigin.VARIABLE.value
        }
        variable_employee: dict[UUID, UUID] = {}
        if variable_ref_ids:
            var_rows = (
                await self.session.execute(
                    _select(PaymentVariableComponent.id, PaymentVariableComponent.employee_id).where(
                        PaymentVariableComponent.id.in_(variable_ref_ids)
                    )
                )
            ).all()
            variable_employee = {cid: eid for cid, eid in var_rows}

        company_ref_ids = {
            s.ref_id
            for s in snaps
            if s.ref_id is not None
            and s.type != PayableSnapshotType.COLLABORATOR
            and (s.origin or "") != PayableOrigin.VARIABLE.value
        }
        item_employee: dict[UUID, UUID] = {}
        if company_ref_ids:
            item_rows = (
                await self.session.execute(
                    _select(CompanyFinancialItem.id, CompanyFinancialItem.employee_id).where(
                        CompanyFinancialItem.id.in_(company_ref_ids),
                        CompanyFinancialItem.employee_id.is_not(None),
                    )
                )
            ).all()
            item_employee = {iid: eid for iid, eid in item_rows}

        def _resolve_employee_id(s: PayableSnapshot) -> UUID | None:
            if (s.origin or "") == PayableOrigin.VARIABLE.value:
                return variable_employee.get(s.ref_id) if s.ref_id is not None else None
            if s.type == PayableSnapshotType.COLLABORATOR:
                return s.ref_id
            return item_employee.get(s.ref_id) if s.ref_id is not None else None

        # 3) Classificação (regra ÚNICA da tela) + agregação por colaborador.
        components_by_emp: dict[UUID, dict[str, float]] = {}
        endiv_by_emp: dict[UUID, float] = {}
        endiv_detalhe_by_emp: dict[UUID, list[tuple[str, float]]] = {}
        distrib_pairs_by_emp: dict[UUID, list[tuple[str, float]]] = {}
        for s in snaps:
            eid = _resolve_employee_id(s)
            if eid is None:
                continue  # lançamento não atribuível a colaborador (não é folha)
            value = round(float(s.amount_final or 0), 2)
            if is_collaborator_payroll(type_=s.type, category=s.category):
                label = _payroll_component_label_from_name(
                    s.name, fallback=PAYROLL_COMPONENT_FALLBACK_LABEL
                )
                bucket = components_by_emp.setdefault(eid, {})
                bucket[label] = round(bucket.get(label, 0.0) + value, 2)
                distrib_pairs_by_emp.setdefault(eid, []).append((s.cost_center or "—", value))
            elif is_employee_debt(type_=s.type, category=s.category):
                endiv_by_emp[eid] = round(endiv_by_emp.get(eid, 0.0) + value, 2)
                descr = (getattr(s, "item_description", None) or s.name or "").strip()
                endiv_detalhe_by_emp.setdefault(eid, []).append((descr, value))
            # demais grupos (Manual, Custo diverso, Veículos, Antecipação): NÃO são folha.

        # 4) Colaboradores com algo a pagar no mês (folha OU endividamento).
        emp_ids = set(components_by_emp) | set(endiv_by_emp)
        emp_by_id: dict[UUID, Employee] = {}
        if emp_ids:
            emps = (
                await self.session.execute(_select(Employee).where(Employee.id.in_(emp_ids)))
            ).scalars().all()
            emp_by_id = {e.id: e for e in emps}

        # Centro de Custo TEMPORAL vigente na competência trabalhada (histórico), em lote.
        from app.services.cost_center_history_service import EmployeeCostCenterService

        cc_by_emp = await EmployeeCostCenterService(self.session).resolve_map(emp_ids, comp)

        ordered_ids = sorted(
            emp_ids,
            key=lambda i: (
                not bool(getattr(emp_by_id.get(i), "is_active", False)),
                (getattr(emp_by_id.get(i), "full_name", "") or "").lower(),
            ),
        )

        # Colunas monetárias = união dos componentes presentes no mês (ordem de aparição).
        # Sem lista fixa: um componente novo no CAP entra sozinho, aqui e na exportação.
        component_columns: list[str] = []
        for eid in ordered_ids:
            for label in components_by_emp.get(eid, {}):
                if label not in component_columns:
                    component_columns.append(label)

        rows: list[dict[str, Any]] = []
        qtd_clt = qtd_pj = 0
        totals_by_component: dict[str, float] = {c: 0.0 for c in component_columns}
        t_endiv = t_geral = 0.0
        for eid in ordered_ids:
            emp = emp_by_id.get(eid)
            if emp is None:
                continue
            tipo = (emp.employment_type or "CLT").strip().upper()
            endiv = round(float(endiv_by_emp.get(eid, 0.0)), 2)
            endiv_itens = [
                {"descricao": d or "Endividamento", "valor": round(float(v), 2)}
                for d, v in endiv_detalhe_by_emp.get(eid, [])
            ]
            if tipo == "PJ":
                qtd_pj += 1
            else:
                qtd_clt += 1

            componentes = components_by_emp.get(eid, {})
            comp_values: dict[str, float | None] = {}
            for coluna in component_columns:
                v = componentes.get(coluna)
                comp_values[coluna] = round(float(v), 2) if v else None
                totals_by_component[coluna] += float(v or 0.0)

            total = round(sum(float(v or 0.0) for v in comp_values.values()) + endiv, 2)
            t_endiv += endiv
            t_geral += total

            rows.append(
                {
                    "nome": emp.full_name,
                    "email": emp.email or "",
                    "cargo": emp.role_title or "",
                    "tipo": tipo,
                    "status": "Ativo" if emp.is_active else "Inativo",
                    # Coluna principal: Centro de Custo cadastrado no colaborador.
                    "centro_custo": (cc_by_emp.get(eid) or "—"),
                    # Coluna auxiliar: distribuição por Centro de Custo, derivada dos próprios
                    # lançamentos do CAP (onde a folha do colaborador foi distribuída).
                    "distribuicao": _payroll_distribution_from_snapshots(
                        distrib_pairs_by_emp.get(eid, [])
                    ),
                    # Componentes da folha (chaves = rótulos dos lançamentos do CAP).
                    "componentes": comp_values,
                    "endividamentos": endiv if endiv > 0 else None,
                    "endividamentos_itens": endiv_itens,
                    "total_folha": total,
                    "pix_tipo": emp.pix_key_type or "",
                    "pix_chave": emp.pix_key or "",
                }
            )

        summary = {
            "competencia": comp_str,
            "scenario": sc.value,
            "qtd_clt": qtd_clt,
            "qtd_pj": qtd_pj,
            "totais_componentes": {c: round(v, 2) for c, v in totals_by_component.items()},
            "total_endividamentos": round(t_endiv, 2),
            "total_geral": round(t_geral, 2),
        }
        if not include_sensitive:
            # Folha sem employees.sensitive: omite valores por linha e zera os totais monetários.
            # A lista de chaves sensíveis é DERIVADA (inclui os componentes dinâmicos), para
            # que um componente novo nasça protegido em vez de vazar por omissão.
            rows = [
                {
                    k: (
                        {c: "" for c in component_columns}
                        if k == "componentes"
                        else ("" if k in self._PAYROLL_REPORT_SENSITIVE_KEYS else v)
                    )
                    for k, v in row.items()
                }
                for row in rows
            ]
            summary = {
                k: (
                    {c: 0 for c in component_columns}
                    if k == "totais_componentes"
                    else (0 if k.startswith("total_") else v)
                )
                for k, v in summary.items()
            }
        return {
            "competencia_ref": comp.isoformat(),
            "scenario": sc.value,
            # Colunas monetárias do mês, na ordem de exibição — a exportação monta o
            # cabeçalho a partir daqui (sem lista fixa).
            "component_columns": component_columns,
            "rows": rows,
            "summary": summary,
        }

    async def generate_vehicles_report(
        self, *, active_only: bool, include_sensitive: bool = True
    ) -> dict[str, Any]:
        rows = await FleetService(self.session).list_vehicles(
            offset=0, limit=10_000, include_inactive=not active_only
        )
        out = []
        for r in rows:
            v = fleet_vehicle_to_read(r)
            out.append(
                {
                    "placa": v.plate,
                    "modelo": getattr(r, "model", None) or "",
                    "descricao": getattr(r, "description", None) or "",
                    "tipo": v.vehicle_type,
                    # Centro de Custo é informação NÃO financeira: sempre presente (independe de sensitive).
                    "centro_custo": v.cost_center or "",
                    "condutor": v.driver_name,
                    # Financeiro: omitido sem vehicles.sensitive (relatório sai sem o custo mensal).
                    "custo_mensal": (float(v.monthly_cost or 0) if include_sensitive else ""),
                    "ativo": v.is_active,
                    "criado_em": r.created_at.isoformat() if getattr(r, "created_at", None) else "",
                    "atualizado_em": r.updated_at.isoformat() if getattr(r, "updated_at", None) else "",
                }
            )
        return {"active_only": active_only, "rows": out}

    async def generate_invoices_report(
        self,
        *,
        project_id: UUID | None,
        status_filter: str | None,
        year: int | None,
        month: int | None,
    ) -> dict[str, Any]:
        if (year is None) != (month is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe ano e mês juntos para o período, ou deixe ambos vazios.",
            )
        svc = ReceivableService(self.session)
        invs = await svc.list_invoices(
            project_id=project_id,
            status=status_filter,
            year=year,
            month=month,
            period_field="issue",
        )
        rows = []
        for inv in invs:
            r = svc.invoice_to_read(inv)
            due = r["due_date"]
            recv = float(r["received_amount"])
            net = float(r["net_amount"])
            rows.append(
                {
                    "projeto": r.get("project_name") or "",
                    "numero_nf": r["number"],
                    "valor_bruto": float(r["gross_amount"]),
                    "vencimento": due.isoformat() if isinstance(due, date) else str(due),
                    "total_recebido": recv,
                    "saldo": max(0.0, net - recv),
                    "status": r["status"],
                }
            )
        return {
            "filters": {
                "project_id": str(project_id) if project_id else None,
                "status": status_filter,
                "year": year,
                "month": month,
            },
            "rows": rows,
        }

    async def generate_debt_report(self, *, competencia: str) -> dict[str, Any]:
        svc = CompanyFinanceService(self.session)
        items = await svc.list_items(tipo="endividamento", competencia=competencia)
        return {"tipo": "endividamento", "competencia": competencia, "items": items}

    async def generate_fixed_costs_report(self, *, competencia: str) -> dict[str, Any]:
        svc = CompanyFinanceService(self.session)
        items = await svc.list_items(tipo="custo_fixo", competencia=competencia)
        return {"tipo": "custo_fixo", "competencia": competencia, "items": items}

    async def generate_dashboard_report(
        self,
        *,
        competencia: date,
        project_id: UUID | None,
        months: int,
        scenario: str | Scenario = DEFAULT_SCENARIO,
    ) -> dict[str, Any]:
        sc = coerce_scenario(scenario)
        dash = DashboardService(self.session)
        comp = normalize_competencia(competencia)
        period_start, period_end = period_last_n_months(comp, months)
        s = await dash.resumo_period(
            project_id=project_id,
            start=period_start,
            end=period_end,
            scenario=sc,
        )
        series_prev = await dash.serie_mensal_interval(
            project_id=project_id,
            start=period_start,
            end=period_end,
            scenario=Scenario.PREVISTO,
        )
        series_real = await dash.serie_mensal_interval(
            project_id=project_id,
            start=period_start,
            end=period_end,
            scenario=Scenario.REALIZADO,
        )
        monthly_for = series_real if sc == Scenario.REALIZADO else series_prev
        lp, lr = await dash.lucro_liquido_previsto_e_realizado_period(
            project_id=project_id,
            start=period_start,
            end=period_end,
        )
        summary = FinancialDashboardSummary(
            scenario=sc.value,
            summary=DirectorSummary.model_validate(s),
            monthly_series=[MonthlyPoint.model_validate(x) for x in monthly_for],
            monthly_series_previsto=[MonthlyPoint.model_validate(x) for x in series_prev],
            monthly_series_realizado=[MonthlyPoint.model_validate(x) for x in series_real],
            period_start=period_start,
            period_end=period_end,
            month_count=len(iter_competencias_inclusive(period_start, period_end)),
            lucro_liquido_previsto=lp,
            lucro_liquido_realizado=lr,
        )
        return {
            "summary": summary.model_dump(mode="json"),
            "months": months,
            "project_id": str(project_id) if project_id else None,
        }

    async def generate_users_report(self) -> dict[str, Any]:
        users = await UsersService(self.session).list_users(offset=0, limit=10_000)
        rows: list[dict[str, Any]] = []
        for u in users:
            role_names = [
                link.role.name
                for link in (getattr(u, "roles", []) or [])
                if getattr(link, "role", None)
            ]
            rows.append(
                {
                    "email": u.email,
                    "nome": u.full_name,
                    "ativo": u.is_active,
                    "papeis": ", ".join(role_names),
                    "criado_em": u.created_at.isoformat() if getattr(u, "created_at", None) else "",
                    "atualizado_em": u.updated_at.isoformat() if getattr(u, "updated_at", None) else "",
                }
            )
        return {"rows": rows}

    async def generate_revenues_report(
        self, *, project_id: UUID | None, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> dict[str, Any]:
        sc = coerce_scenario(scenario)
        rows = await FinancialCrudService(self.session).list_revenues(
            offset=0, limit=10_000, project_id=project_id, scenario=sc
        )
        # Resolve nomes de projeto em lote (relatório legível, sem UUID cru).
        from sqlalchemy import select as _select

        pids = {r.project_id for r in rows if r.project_id}
        project_names: dict[UUID, str] = {}
        if pids:
            prows = (await self.session.execute(_select(Project).where(Project.id.in_(pids)))).scalars().all()
            project_names = {p.id: p.name for p in prows}
        out: list[dict[str, Any]] = []
        for r in rows:
            comp = r.competencia
            scen = r.scenario.value if hasattr(r.scenario, "value") else str(r.scenario)
            out.append(
                {
                    "projeto": project_names.get(r.project_id) or "",
                    "project_id": str(r.project_id),
                    "competencia": comp.isoformat() if isinstance(comp, date) else str(comp),
                    "cenario": scen,
                    "valor": float(r.amount),
                    "descricao": r.description or "",
                    "status": r.status,
                    "retencao": bool(r.has_retention),
                    "criado_em": r.created_at.isoformat() if getattr(r, "created_at", None) else "",
                    "atualizado_em": r.updated_at.isoformat() if getattr(r, "updated_at", None) else "",
                }
            )
        return {
            "filters": {"project_id": str(project_id) if project_id else None, "scenario": sc.value},
            "rows": out,
        }


async def list_project_ids_for_user(session: AsyncSession, user: User) -> list[UUID]:
    from app.api.deps import get_accessible_project_ids

    return await get_accessible_project_ids(user, session)
