from __future__ import annotations

import io
from datetime import date
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_current_workspace,
    require_project_access,
    user_has_any_permission,
    user_has_permission,
    user_sees_all_projects,
)
from app.core.permission_codes import (
    ASSETS_READ,
    ASSETS_SENSITIVE,
    BILLING_READ,
    COMPANY_FINANCE_READ,
    DASHBOARD_READ,
    DEBTS_READ,
    EMPLOYEES_EXPORT,
    EMPLOYEES_SENSITIVE,
    INVOICES_READ,
    PAYABLES_READ,
    RECEIVABLES_READ,
    REPORTS_EXPORT,
    REPORTS_READ,
    USERS_MANAGE,
    VEHICLES_EXPORT,
    VEHICLES_SENSITIVE,
)
from app.core.scenario import Scenario, coerce_scenario
from app.database.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.reports import ReportGenerateRequest
from app.services.export.report_meta import (
    ReportContext,
    month_year_label,
    month_year_token,
)
from app.services.operational_report_export import render_operational_report_bytes
from app.services.operational_report_service import OperationalReportService, resolve_project_access
from app.services.report_export import render_report_bytes
from app.services.report_service import (
    ReportService,
    _competencia_date,
    _uuid,
    list_project_ids_for_user,
)
from app.utils.date_utils import normalize_competencia

router = APIRouter(tags=["reports"])

_INVOICE_REPORT_STATUSES = frozenset({"EMITIDA", "ANTECIPADA", "FINALIZADA", "CANCELADA"})


def _report_scenario(body: ReportGenerateRequest) -> Scenario:
    """Corpo `scenario` tem prioridade sobre `filters.scenario`; omissão → REALIZADO."""
    if body.scenario is not None and str(body.scenario).strip():
        return coerce_scenario(str(body.scenario).strip())
    return coerce_scenario(body.filters.get("scenario"))


def _assert_report_access(user: User) -> None:
    if not user_has_any_permission(user, REPORTS_READ, REPORTS_EXPORT):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")


# Isolamento de módulos nos Relatórios: além de reports.view/export, cada tipo de relatório exige
# a permissão VIEW do SEU módulo. Antes, quem tivesse apenas reports.view conseguia gerar o
# relatório de qualquer módulo (ex.: Ativos) sem ter a permissão daquele módulo.
# project_summary/company_summary ficam fora do mapa: são consolidações multi-módulo já
# protegidas por reports.* (+ require_project_access no project_summary).
_REPORT_TYPE_VIEW_PERMISSION: dict[str, str] = {
    "payables_detailed": PAYABLES_READ,
    "receivables_detailed": RECEIVABLES_READ,
    "invoices_detailed": INVOICES_READ,
    "invoices": INVOICES_READ,
    "debt": DEBTS_READ,
    "fixed_costs": COMPANY_FINANCE_READ,
    "revenues": BILLING_READ,
    # Exportações de recurso específico usam <recurso>.export (não reports.export).
    "vehicles": VEHICLES_EXPORT,
    "employees": EMPLOYEES_EXPORT,
    "payroll": EMPLOYEES_EXPORT,
    "users": USERS_MANAGE,
    "dashboard": DASHBOARD_READ,
    "assets_inventory": ASSETS_READ,
    "assets_in_use": ASSETS_READ,
    "assets_inspections": ASSETS_READ,
    "assets_movements": ASSETS_READ,
}


def _assert_report_type_access(user: User, report_type: str) -> None:
    """Autoriza a geração de um relatório: reports.view/export E a permissão do módulo do tipo."""
    _assert_report_access(user)
    needed = _REPORT_TYPE_VIEW_PERMISSION.get(report_type)
    if needed is not None and not user_has_permission(user, needed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para o módulo correspondente a este relatório.",
        )


# Relatórios que possuem cenário Previsto/Realizado (para o cabeçalho de identificação).
_SCENARIO_REPORTS = frozenset(
    {"project_summary", "company_summary", "employees", "payroll", "revenues", "dashboard"}
)


def _stream(data: bytes, filename: str, media: str) -> StreamingResponse:
    # RFC 5987: nome amigável em pt-BR (acentos/espaços) via filename*, com
    # fallback ASCII em filename para clientes antigos.
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "relatorio"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": disposition},
    )


def _period_from_filters(f: dict) -> tuple[str | None, str | None]:
    """Deriva rótulo humano e token de arquivo do período, a partir dos filtros.

    Suporta competência única, ano/mês e intervalo mês–mês (payables/movimentações).
    Retorna (rótulo p/ cabeçalho, token p/ nome de arquivo) ou (None, None).
    """

    def _month(raw) -> date | None:
        if raw in (None, ""):
            return None
        s = str(raw).strip()
        if len(s) >= 7 and s[4] == "-":
            return date(int(s[:4]), int(s[5:7]), 1)
        return None

    start = _month(f.get("competencia")) or _month(f.get("month"))
    if start is None and f.get("year") and f.get("month"):
        try:
            start = date(int(f["year"]), int(f["month"]), 1)
        except (ValueError, TypeError):
            start = None
    end = _month(f.get("month_to"))
    if start is None:
        return None, None
    if end and (end.year, end.month) != (start.year, start.month):
        return (
            f"{month_year_label(start)} a {month_year_label(end)}",
            f"{month_year_token(start)} a {month_year_token(end)}",
        )
    return month_year_label(start), month_year_token(start)


async def _build_ctx(
    db: AsyncSession, report_type: str, user: User, filters: dict, scenario: Scenario | None
) -> ReportContext:
    """Monta o contexto de identificação (item 8) da exportação — só rotulagem."""
    projeto = None
    pid_raw = filters.get("project_id")
    if pid_raw:
        try:
            proj = await db.get(Project, UUID(str(pid_raw)))
            projeto = proj.name if proj else None
        except (ValueError, TypeError):
            projeto = None
    periodo, token = _period_from_filters(filters)
    return ReportContext(
        report_type=report_type,
        generated_by=(user.full_name or user.email),
        filters=dict(filters or {}),
        projeto=projeto,
        periodo=periodo,
        periodo_token=token,
        cenario=(scenario.value if (scenario and report_type in _SCENARIO_REPORTS) else None),
    )


@router.post("/generate")
async def generate_report(
    body: ReportGenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _ws: str = Depends(get_current_workspace),
) -> StreamingResponse:
    """Gera relatório (Excel ou PDF) conforme tipo e filtros."""
    # Isolamento de módulos: exige a permissão do módulo do relatório (além de reports.*).
    _assert_report_type_access(user, body.type)
    f = body.filters
    fmt = body.format
    svc = ReportService(db)
    ctx = await _build_ctx(db, body.type, user, f, _report_scenario(body))

    if body.type == "project_summary":
        _assert_report_access(user)
        pid = _uuid(f, "project_id")
        if pid is None:
            raise HTTPException(status_code=400, detail="Informe project_id.")
        await require_project_access(project_id=pid, user=user, db=db)
        comp = _competencia_date(f, "competencia")
        if comp is None:
            raise HTTPException(status_code=400, detail="Informe competencia (YYYY-MM).")
        payload = await svc.generate_project_summary(
            project_id=pid, competencia=comp, scenario=_report_scenario(body)
        )
        raw, name, media = render_report_bytes("project_summary", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "company_summary":
        _assert_report_access(user)
        comp = _competencia_date(f, "competencia")
        if comp is None:
            raise HTTPException(status_code=400, detail="Informe competencia (YYYY-MM).")
        if _uuid(f, "project_id") is not None:
            pid = _uuid(f, "project_id")
            assert pid is not None
            await require_project_access(project_id=pid, user=user, db=db)
            pids = [pid]
        else:
            pids = await list_project_ids_for_user(db, user)
        payload = await svc.generate_company_summary(
            competencia=comp, project_ids=pids, scenario=_report_scenario(body)
        )
        raw, name, media = render_report_bytes("company_summary", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "employees":
        _assert_report_access(user)
        if not user_has_any_permission(user, EMPLOYEES_EXPORT):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        comp = _competencia_date(f, "competencia")
        # Sem employees.sensitive, o relatório sai SEM valores financeiros (salários/custos zerados).
        include_sensitive = user_has_permission(user, EMPLOYEES_SENSITIVE)
        payload = await svc.generate_employees_report(
            competencia=comp, scenario=_report_scenario(body), include_sensitive=include_sensitive
        )
        raw, name, media = render_report_bytes("employees", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "payroll":
        _assert_report_access(user)
        if not user_has_any_permission(user, EMPLOYEES_EXPORT):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        comp = _competencia_date(f, "competencia")
        include_sensitive = user_has_permission(user, EMPLOYEES_SENSITIVE)
        payload = await svc.generate_payroll_report(
            competencia=comp, scenario=_report_scenario(body), include_sensitive=include_sensitive
        )
        raw, name, media = render_report_bytes("payroll", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "vehicles":
        _assert_report_access(user)
        if not user_has_any_permission(user, VEHICLES_EXPORT):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        active_only = bool(f.get("active_only", False))
        # Sem vehicles.sensitive, o relatório sai SEM o custo mensal (valor financeiro omitido).
        include_sensitive = user_has_permission(user, VEHICLES_SENSITIVE)
        payload = await svc.generate_vehicles_report(active_only=active_only, include_sensitive=include_sensitive)
        raw, name, media = render_report_bytes("vehicles", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "invoices":
        _assert_report_access(user)
        if not user_has_any_permission(user, INVOICES_READ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        project_id = _uuid(f, "project_id")
        st = f.get("status")
        if st is not None and str(st).strip() != "" and str(st) not in _INVOICE_REPORT_STATUSES:
            raise HTTPException(status_code=400, detail="status inválido.")
        status_filter = str(st).strip() if st is not None and str(st).strip() != "" else None
        year = f.get("year")
        month = f.get("month")
        yi = int(year) if year is not None else None
        mi = int(month) if month is not None else None
        payload = await svc.generate_invoices_report(
            project_id=project_id,
            status_filter=status_filter,
            year=yi,
            month=mi,
        )
        raw, name, media = render_report_bytes("invoices", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "debt":
        _assert_report_access(user)
        if not user_has_any_permission(user, DEBTS_READ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        comp = f.get("competencia")
        if not comp or not str(comp).strip():
            raise HTTPException(status_code=400, detail="Informe competencia (YYYY-MM).")
        payload = await svc.generate_debt_report(competencia=str(comp).strip()[:7])
        raw, name, media = render_report_bytes("debt", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "fixed_costs":
        _assert_report_access(user)
        if not user_has_any_permission(user, COMPANY_FINANCE_READ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        comp = f.get("competencia")
        if not comp or not str(comp).strip():
            raise HTTPException(status_code=400, detail="Informe competencia (YYYY-MM).")
        payload = await svc.generate_fixed_costs_report(competencia=str(comp).strip()[:7])
        raw, name, media = render_report_bytes("fixed_costs", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "users":
        _assert_report_access(user)
        if not user_has_any_permission(user, USERS_MANAGE):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        payload = await svc.generate_users_report()
        raw, name, media = render_report_bytes("users", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "revenues":
        _assert_report_access(user)
        if not user_has_any_permission(user, BILLING_READ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        project_id = _uuid(f, "project_id")
        payload = await svc.generate_revenues_report(
            project_id=project_id, scenario=_report_scenario(body)
        )
        raw, name, media = render_report_bytes("revenues", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "dashboard":
        _assert_report_access(user)
        can_global = user_sees_all_projects(user)
        project_id = _uuid(f, "project_id")
        if project_id is None and not can_global:
            raise HTTPException(status_code=400, detail="Informe project_id para exportar o dashboard.")
        if project_id is not None:
            await require_project_access(project_id=project_id, user=user, db=db)
        today = date.today()
        comp_raw = f.get("competencia")
        if comp_raw:
            comp = _competencia_date(f, "competencia")
            if comp is None:
                raise HTTPException(status_code=400, detail="competencia inválida.")
            comp_n = normalize_competencia(comp)
        else:
            comp_n = date(today.year, today.month, 1)
        months = int(f.get("months") or 6)
        if months < 1 or months > 24:
            raise HTTPException(status_code=400, detail="months deve ser entre 1 e 24.")
        payload = await svc.generate_dashboard_report(
            competencia=comp_n,
            project_id=project_id,
            months=months,
            scenario=_report_scenario(body),
        )
        raw, name, media = render_report_bytes("dashboard", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "payables_detailed":
        _assert_report_access(user)
        if not user_has_any_permission(user, PAYABLES_READ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        sees_all, allowed = await resolve_project_access(db, user)
        payload = await OperationalReportService(db).generate_payables_detailed(
            filters=f,
            accessible_project_ids=allowed,
            sees_all_projects=sees_all,
        )
        await db.commit()
        raw, name, media = render_operational_report_bytes("payables_detailed", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "receivables_detailed":
        _assert_report_access(user)
        if not user_has_any_permission(user, RECEIVABLES_READ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        sees_all, allowed = await resolve_project_access(db, user)
        payload = await OperationalReportService(db).generate_receivables_detailed(
            filters=f,
            workspace_id=_ws,
            accessible_project_ids=allowed,
            sees_all_projects=sees_all,
        )
        raw, name, media = render_operational_report_bytes("receivables_detailed", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type == "invoices_detailed":
        _assert_report_access(user)
        if not user_has_any_permission(user, INVOICES_READ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        sees_all, allowed = await resolve_project_access(db, user)
        payload = await OperationalReportService(db).generate_invoices_detailed(
            filters=f,
            accessible_project_ids=allowed,
            sees_all_projects=sees_all,
        )
        raw, name, media = render_operational_report_bytes("invoices_detailed", payload, fmt, ctx)
        return _stream(raw, name, media)

    if body.type in (
        "assets_inventory",
        "assets_in_use",
        "assets_inspections",
        "assets_movements",
    ):
        _assert_report_access(user)
        if not user_has_any_permission(user, ASSETS_READ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        ops = OperationalReportService(db)
        # Sem assets.sensitive, os valores financeiros do relatório saem omitidos (só quantitativo).
        include_sensitive = user_has_permission(user, ASSETS_SENSITIVE)
        if body.type == "assets_inventory":
            payload = await ops.generate_assets_inventory(filters=f, include_sensitive=include_sensitive)
        elif body.type == "assets_in_use":
            payload = await ops.generate_assets_in_use(filters=f, include_sensitive=include_sensitive)
        elif body.type == "assets_inspections":
            payload = await ops.generate_assets_inspections(filters=f)
        else:
            payload = await ops.generate_assets_movements(filters=f)
        raw, name, media = render_operational_report_bytes(body.type, payload, fmt, ctx)
        return _stream(raw, name, media)

    raise HTTPException(status_code=400, detail="Tipo de relatório desconhecido.")
