from __future__ import annotations

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
from app.services.employee_cost_service import pj_cost_breakdown
from app.services.fleet_service import FleetService, fleet_vehicle_to_read
from app.services.project_structure_service import ProjectStructureService
from app.services.projects_service import ProjectsService
from app.services.financial_crud_service import FinancialCrudService
from app.services.payroll_service import PayrollService
from app.services.receivable_service import ReceivableService
from app.services.users_service import UsersService
from app.core.scenario import DEFAULT_SCENARIO, Scenario, coerce_scenario
from app.utils.date_utils import iter_competencias_inclusive, normalize_competencia, period_last_n_months


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


def _month_bounds_local(comp: date) -> tuple[date, date]:
    from calendar import monthrange

    last = monthrange(comp.year, comp.month)[1]
    return date(comp.year, comp.month, 1), date(comp.year, comp.month, last)


def _debt_monthly_value(item: Any) -> float:
    """Valor mensal de um endividamento vinculado ao colaborador (parcela ou referência).

    Mesma base já usada pelas pendências/CAP: parcela (installment_value) quando há
    renegociação parcelada; senão saldo renegociado / valor de referência.
    """
    rt = getattr(item, "renegotiation_type", None)
    rt_val = getattr(rt, "value", rt)
    if (
        getattr(item, "has_renegotiation", False)
        and rt_val == "INSTALLMENTS"
        and getattr(item, "installment_value", None) is not None
    ):
        return float(item.installment_value)
    if getattr(item, "has_renegotiation", False) and getattr(item, "renegotiated_amount", None) is not None:
        return float(item.renegotiated_amount)
    return float(getattr(item, "valor_referencia", 0) or 0)


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

    async def generate_employees_report(
        self, *, competencia: date | None, scenario: str | Scenario = DEFAULT_SCENARIO
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
        return {"competencia_ref": comp.isoformat(), "scenario": sc.value, "rows": rows}

    async def generate_payroll_report(
        self, *, competencia: date | None, scenario: str | Scenario = DEFAULT_SCENARIO
    ) -> dict[str, Any]:
        """Folha de Pagamento (fechamento mensal): 1 linha por colaborador com o valor
        efetivamente pago na competência (holerite real CLT / contratado PJ + VR +
        ajuda de custo + endividamentos). Consolida tudo no backend (sem N+1).

        NÃO altera o relatório de Colaboradores nem qualquer cálculo existente — só lê
        os dados atuais (payroll, holerite real e endividamentos vinculados).
        """
        from sqlalchemy import select as _select
        from app.models.employee import Employee
        from app.models.employee_monthly_payroll_override import EmployeeMonthlyPayrollOverride
        from app.models.company_finance import CompanyFinancialItem

        comp = normalize_competencia(competencia or default_cost_reference())
        sc = coerce_scenario(scenario)
        comp_str = f"{comp.year:04d}-{comp.month:02d}"
        _, month_end = _month_bounds_local(comp)

        # 1) Payroll consolidado (distribuição por projeto/administrativo + conjunto base).
        payroll = await PayrollService(self.session).build_payroll(
            competencia=comp, scenario=sc, project_id=None
        )
        line_by_emp = {line.employee_id: line for line in payroll.lines}

        # 2) Holerite real (líquido + VR) da competência — 1 consulta.
        overrides = (
            await self.session.execute(
                _select(EmployeeMonthlyPayrollOverride).where(
                    EmployeeMonthlyPayrollOverride.competence_month == comp_str
                )
            )
        ).scalars().all()
        override_by_emp = {o.employee_id: o for o in overrides}

        # 3) Endividamentos vinculados ao colaborador, vigentes na competência — 1 consulta.
        endiv_items = (
            await self.session.execute(
                _select(CompanyFinancialItem).where(
                    CompanyFinancialItem.tipo == "endividamento",
                    CompanyFinancialItem.employee_id.is_not(None),
                    CompanyFinancialItem.is_active.is_(True),
                    (CompanyFinancialItem.start_date.is_(None))
                    | (CompanyFinancialItem.start_date <= month_end),
                    (CompanyFinancialItem.end_date.is_(None))
                    | (CompanyFinancialItem.end_date >= comp),
                )
            )
        ).scalars().all()
        endiv_by_emp: dict[UUID, float] = {}
        # Detalhe por colaborador: (descrição, valor) de cada endividamento vinculado, para a
        # coluna "Detalhamento dos Endividamentos". A descrição usa item_description (novo);
        # cai para o nome legado quando o item antigo não tem descrição própria.
        endiv_detalhe_by_emp: dict[UUID, list[tuple[str, float]]] = {}
        for it in endiv_items:
            val = _debt_monthly_value(it)
            endiv_by_emp[it.employee_id] = endiv_by_emp.get(it.employee_id, 0.0) + val
            descr = (getattr(it, "item_description", None) or it.nome or "").strip()
            endiv_detalhe_by_emp.setdefault(it.employee_id, []).append((descr, val))

        # 3b) Custos fixos vinculados ao colaborador (COLABORADOR_MATRIZ), vigentes — 1 consulta.
        custofixo_ids = set(
            (
                await self.session.execute(
                    _select(CompanyFinancialItem.employee_id).where(
                        CompanyFinancialItem.tipo == "custo_fixo",
                        CompanyFinancialItem.employee_id.is_not(None),
                        CompanyFinancialItem.is_active.is_(True),
                        (CompanyFinancialItem.start_date.is_(None))
                        | (CompanyFinancialItem.start_date <= month_end),
                        (CompanyFinancialItem.end_date.is_(None))
                        | (CompanyFinancialItem.end_date >= comp),
                    )
                )
            ).scalars().all()
        )

        # 3c) Centros de custo dos projetos alocados (para a coluna opcional "Distribuição").
        proj_ids = {
            s.project_id for line in payroll.lines for s in (line.by_project or []) if s.project_id
        }
        proj_cc: dict[UUID, str] = {}
        if proj_ids:
            prows = (
                await self.session.execute(_select(Project).where(Project.id.in_(proj_ids)))
            ).scalars().all()
            proj_cc = {p.id: (p.cost_center or "") for p in prows}

        # 4) SOMENTE colaboradores com MOVIMENTAÇÃO na competência (regra do relatório):
        #    custo em projeto/administrativo (payroll com total > 0) OU holerite OU
        #    endividamento OU custo fixo vinculado. Elimina desligados/sem uso/esquecidos.
        moved_ids = {eid for eid, ln in line_by_emp.items() if float(getattr(ln, "grand_total", 0) or 0) > 0}
        moved_ids |= set(override_by_emp) | set(endiv_by_emp) | custofixo_ids
        emp_ids = moved_ids
        emp_by_id: dict[UUID, Employee] = {}
        if emp_ids:
            emps = (
                await self.session.execute(_select(Employee).where(Employee.id.in_(emp_ids)))
            ).scalars().all()
            emp_by_id = {e.id: e for e in emps}

        # Centro de Custo TEMPORAL: resolve o centro VIGENTE na competência do relatório
        # (histórico), em lote (sem N+1). Não usa mais o cache `employees.cost_center`.
        from app.services.cost_center_history_service import EmployeeCostCenterService

        cc_by_emp = await EmployeeCostCenterService(self.session).resolve_map(emp_ids, comp)

        ordered_ids = sorted(
            emp_ids,
            key=lambda i: (
                not bool(getattr(emp_by_id.get(i), "is_active", False)),
                (getattr(emp_by_id.get(i), "full_name", "") or "").lower(),
            ),
        )

        rows: list[dict[str, Any]] = []
        qtd_clt = qtd_pj = 0
        t_sal = t_ben = t_vr = t_endiv = t_ajuda = t_geral = 0.0
        for eid in ordered_ids:
            emp = emp_by_id.get(eid)
            if emp is None:
                continue
            line = line_by_emp.get(eid)
            tipo = (emp.employment_type or "CLT").strip().upper()
            ov = override_by_emp.get(eid)
            endiv = round(float(endiv_by_emp.get(eid, 0.0)), 2)
            endiv_itens = [
                {"descricao": d or "Endividamento", "valor": round(float(v), 2)}
                for d, v in endiv_detalhe_by_emp.get(eid, [])
            ]

            if tipo == "PJ":
                qtd_pj += 1
                pj = pj_cost_breakdown(emp)
                salario_base = round(float(pj["salary_base"]), 2)
                salario_pago = salario_base  # PJ: valor contratado é o que se paga
                vr_real = None
                ajuda = round(float(pj["ajuda_custo"]), 2)
            else:
                qtd_clt += 1
                salario_base = float(emp.salary_base) if emp.salary_base is not None else None
                # "Real": só quando há holerite lançado (senão em branco).
                salario_pago = (
                    round(float(ov.net_salary_amount), 2)
                    if (ov is not None and ov.net_salary_amount is not None)
                    else None
                )
                vr_real = (
                    round(float(ov.vr_amount), 2)
                    if (ov is not None and ov.vr_amount is not None)
                    else None
                )
                ajuda = None

            beneficios = None  # módulo de benefícios futuro (coluna preservada)
            total = round(
                (salario_pago or 0.0) + (vr_real or 0.0) + (beneficios or 0.0) + (ajuda or 0.0) + endiv,
                2,
            )

            t_sal += salario_pago or 0.0
            t_vr += vr_real or 0.0
            t_ben += beneficios or 0.0
            t_ajuda += ajuda or 0.0
            t_endiv += endiv
            t_geral += total

            rows.append(
                {
                    "nome": emp.full_name,
                    "email": emp.email or "",
                    "cargo": emp.role_title or "",
                    "tipo": tipo,
                    "status": "Ativo" if emp.is_active else "Inativo",
                    # Coluna principal: Centro de Custo cadastrado no colaborador (Parte 6).
                    "centro_custo": (cc_by_emp.get(eid) or "—"),
                    # Coluna auxiliar (opcional): distribuição por Centro de Custo (Parte 7),
                    # derivada da alocação em projetos — informação preservada.
                    "distribuicao": _payroll_cost_center_distribution(line, proj_cc),
                    "salario_base": salario_base,
                    "salario_liquido": salario_pago,
                    "beneficios": beneficios,
                    "vr": vr_real,
                    "vt": None,  # futuro
                    "ajuda_custo": ajuda,
                    "endividamentos": endiv if endiv > 0 else None,
                    # Itens individuais para a coluna "Detalhamento dos Endividamentos"
                    # (formatação/summarização feita no render). Vazio quando não há.
                    "endividamentos_itens": endiv_itens,
                    "outros": None,  # futuro
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
            "total_salarios": round(t_sal, 2),
            "total_beneficios": round(t_ben, 2),
            "total_vr": round(t_vr, 2),
            "total_endividamentos": round(t_endiv, 2),
            "total_ajuda_custo": round(t_ajuda, 2),
            "total_geral": round(t_geral, 2),
        }
        return {"competencia_ref": comp.isoformat(), "scenario": sc.value, "rows": rows, "summary": summary}

    async def generate_vehicles_report(self, *, active_only: bool) -> dict[str, Any]:
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
                    "condutor": v.driver_name,
                    "custo_mensal": float(v.monthly_cost or 0),
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
