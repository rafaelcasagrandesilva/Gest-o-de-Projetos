from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.permission_codes import EMPLOYEES_VIEW
from app.database.session import get_db
from app.schemas.employees import EmployeeRead
from app.services.employees_service import EmployeesService, default_cost_reference


router = APIRouter()


@router.get("", response_model=list[EmployeeRead], dependencies=[Depends(require_permission(EMPLOYEES_VIEW))])
async def list_collaborators(
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(default=None, description="Busca por nome (ILIKE em full_name)."),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    competencia: date | None = Query(default=None, description="Competência para custo (opcional)."),
) -> list[EmployeeRead]:
    comp = competencia or default_cost_reference()
    return await EmployeesService(db).list_employees_as_read(offset=offset, limit=limit, competencia=comp, search=search)


@router.get("/search", response_model=list[dict], dependencies=[Depends(require_permission(EMPLOYEES_VIEW))])
async def search_collaborators(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[dict]:
    """
    Endpoint leve para selects/autocomplete.
    Retorna apenas {id, name}.
    """
    term = (q or "").strip()
    if not term:
        return []
    rows = await EmployeesService(db).list_employees(offset=0, limit=limit, search=term)
    return [{"id": str(r.id), "name": r.full_name} for r in rows if getattr(r, "full_name", None)]

