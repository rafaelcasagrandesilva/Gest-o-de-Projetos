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
    project_id: UUID | None = Query(
        default=None,
        description="Filtra por Centro de Custo do projeto (Mão de Obra). Omitido = todos.",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    competencia: date | None = Query(default=None, description="Competência para custo (opcional)."),
) -> list[EmployeeRead]:
    comp = competencia or default_cost_reference()
    svc = EmployeesService(db)
    cc = await svc.cost_center_for_project(project_id) if project_id is not None else None
    return await svc.list_employees_as_read(
        offset=offset, limit=limit, competencia=comp, search=search, cost_center=cc
    )


@router.get("/search", response_model=list[dict], dependencies=[Depends(require_permission(EMPLOYEES_VIEW))])
async def search_collaborators(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, max_length=255),
    project_id: UUID | None = Query(
        default=None,
        description="Filtra por Centro de Custo do projeto. Omitido = todos (compatível).",
    ),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[dict]:
    """
    Endpoint leve para selects/autocomplete.
    Retorna apenas {id, name}. Com `project_id`, filtra pelo Centro de Custo do projeto.
    """
    term = (q or "").strip()
    if not term:
        return []
    svc = EmployeesService(db)
    cc = await svc.cost_center_for_project(project_id) if project_id is not None else None
    rows = await svc.list_employees(offset=0, limit=limit, search=term, cost_center=cc)
    return [{"id": str(r.id), "name": r.full_name} for r in rows if getattr(r, "full_name", None)]


@router.get(
    "/cost-centers",
    response_model=list[str],
    dependencies=[Depends(require_permission(EMPLOYEES_VIEW))],
)
async def list_cost_centers(db: AsyncSession = Depends(get_db)) -> list[str]:
    """Centros de Custo distintos existentes (projetos + colaboradores) para o datalist do cadastro."""
    from sqlalchemy import select as _select
    from app.models.project import Project
    from app.models.employee import Employee

    # Centro de Custo efetivo dos projetos = cost_center (se houver) senão o nome do projeto.
    prows = (await db.execute(_select(Project.cost_center, Project.name))).all()
    emp_cc = (
        await db.execute(_select(Employee.cost_center).where(Employee.cost_center.is_not(None)).distinct())
    ).scalars().all()
    values: set[str] = set()
    for cc, name in prows:
        eff = (cc or "").strip() or (name or "").strip()
        if eff:
            values.add(eff)
    for c in emp_cc:
        if c and str(c).strip():
            values.add(str(c).strip())
    return sorted(values, key=lambda s: s.lower())

