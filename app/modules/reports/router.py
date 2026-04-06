from __future__ import annotations

import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    require_project_access,
    user_has_any_permission,
    user_sees_all_projects,
)
from app.core.permission_codes import (
    BILLING_VIEW,
    COMPANY_FINANCE_VIEW,
    DEBTS_VIEW,
    EMPLOYEES_VIEW,
    INVOICES_VIEW,
    REPORTS_EXPORT,
    REPORTS_VIEW,
    USERS_MANAGE,
    VEHICLES_VIEW,
)
from app.core.scenario import Scenario, coerce_scenario
from app.database.session import get_db
from app.models.user import User
from app.schemas.reports import ReportGenerateRequest
from app.services.report_export import render_report_bytes
from app.services.report_service import (
    ReportService,
    _competencia_date,
    _uuid,
    list_project_ids_for_user,
)
from app.utils.date_utils import normalize_competencia

router = APIRouter(tags=["reports"])


def _report_scenario(body: ReportGenerateRequest) -> Scenario:
    """Corpo `scenario` tem prioridade sobre `filters.scenario`; omissão → REALIZADO."""
    if body.scenario is not None and str(body.scenario).strip():
        return coerce_scenario(str(body.scenario).strip())
    return coerce_scenario(body.filters.get("scenario"))


def _assert_report_access(user: User) -> None:
    if not user_has_any_permission(user, REPORTS_VIEW, REPORTS_EXPORT):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")


def _stream(data: bytes, filename: str, media: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/generate")
async def generate_report(
    body: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Gera relatório (Excel ou PDF) conforme tipo e filtros."""
    f = body.filters
    fmt = body.format
    svc = ReportService(db)

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
        raw, name, media = render_report_bytes("project_summary", payload, fmt)
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
        raw, name, media = render_report_bytes("company_summary", payload, fmt)
        return _stream(raw, name, media)

    if body.type == "employees":
        _assert_report_access(user)
        if not user_has_any_permission(user, EMPLOYEES_VIEW):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        comp = _competencia_date(f, "competencia")
        payload = await svc.generate_employees_report(competencia=comp, scenario=_report_scenario(body))
        raw, name, media = render_report_bytes("employees", payload, fmt)
        return _stream(raw, name, media)

    if body.type == "vehicles":
        _assert_report_access(user)
        if not user_has_any_permission(user, VEHICLES_VIEW):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        active_only = bool(f.get("active_only", False))
        payload = await svc.generate_vehicles_report(active_only=active_only)
        raw, name, media = render_report_bytes("vehicles", payload, fmt)
        return _stream(raw, name, media)

    if body.type == "invoices":
        _assert_report_access(user)
        if not user_has_any_permission(user, INVOICES_VIEW):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        project_id = _uuid(f, "project_id")
        st = f.get("status")
        if st is not None and str(st).strip() != "" and str(st) not in ("PAGA", "PENDENTE", "ATRASADA"):
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
        raw, name, media = render_report_bytes("invoices", payload, fmt)
        return _stream(raw, name, media)

    if body.type == "debt":
        _assert_report_access(user)
        if not user_has_any_permission(user, DEBTS_VIEW):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        comp = f.get("competencia")
        if not comp or not str(comp).strip():
            raise HTTPException(status_code=400, detail="Informe competencia (YYYY-MM).")
        payload = await svc.generate_debt_report(competencia=str(comp).strip()[:7])
        raw, name, media = render_report_bytes("debt", payload, fmt)
        return _stream(raw, name, media)

    if body.type == "fixed_costs":
        _assert_report_access(user)
        if not user_has_any_permission(user, COMPANY_FINANCE_VIEW):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        comp = f.get("competencia")
        if not comp or not str(comp).strip():
            raise HTTPException(status_code=400, detail="Informe competencia (YYYY-MM).")
        payload = await svc.generate_fixed_costs_report(competencia=str(comp).strip()[:7])
        raw, name, media = render_report_bytes("fixed_costs", payload, fmt)
        return _stream(raw, name, media)

    if body.type == "users":
        _assert_report_access(user)
        if not user_has_any_permission(user, USERS_MANAGE):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        payload = await svc.generate_users_report()
        raw, name, media = render_report_bytes("users", payload, fmt)
        return _stream(raw, name, media)

    if body.type == "revenues":
        _assert_report_access(user)
        if not user_has_any_permission(user, BILLING_VIEW):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para este relatório.")
        project_id = _uuid(f, "project_id")
        payload = await svc.generate_revenues_report(
            project_id=project_id, scenario=_report_scenario(body)
        )
        raw, name, media = render_report_bytes("revenues", payload, fmt)
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
        raw, name, media = render_report_bytes("dashboard", payload, fmt)
        return _stream(raw, name, media)

    raise HTTPException(status_code=400, detail="Tipo de relatório desconhecido.")
