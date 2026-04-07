from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_may_write_scenario,
    default_scenario_for_create,
    get_current_user,
    require_permission,
    require_project_access,
    user_sees_all_projects,
)
from app.core.permission_codes import (
    EMPLOYEES_EDIT,
    EMPLOYEES_VIEW,
    PROJECTS_CREATE,
    PROJECTS_DELETE,
    PROJECTS_EDIT,
    PROJECTS_VIEW,
    USERS_MANAGE,
)
from app.core.scenario import coerce_scenario, parse_scenario
from app.database.session import get_db
from app.models.user import ProjectUser, User
from app.schemas.employees import EmployeeAllocationCreate, EmployeeAllocationRead
from app.schemas.projects import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.employees_service import EmployeesService
from app.services.projects_service import ProjectsService


router = APIRouter()


@router.get("/", response_model=list[ProjectRead], dependencies=[Depends(require_permission(PROJECTS_VIEW))])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ProjectRead]:
    svc = ProjectsService(db)
    if user_sees_all_projects(user):
        rows = await svc.list_projects(offset=offset, limit=limit)
    else:
        rows = await svc.list_projects_for_user(user_id=user.id, offset=offset, limit=limit)
    return [ProjectRead.model_validate(p) for p in rows]


@router.get(
    "/{project_id}/allocations",
    response_model=list[EmployeeAllocationRead],
    dependencies=[Depends(require_permission(EMPLOYEES_VIEW))],
)
async def list_project_allocations(
    project_id: UUID,
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
    competencia: date | None = Query(
        default=None,
        description="Primeiro dia do mês: retorna apenas alocações ativas nesta competência.",
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> list[EmployeeAllocationRead]:
    scenario = coerce_scenario(scenario_param)
    rows = await EmployeesService(db).list_allocations_by_project(
        project_id=project_id, scenario=scenario, competencia=competencia
    )
    return [EmployeeAllocationRead.model_validate(r) for r in rows]


@router.post(
    "/{project_id}/allocations",
    response_model=EmployeeAllocationRead,
    dependencies=[Depends(require_permission(EMPLOYEES_EDIT))],
)
async def create_project_allocation(
    project_id: UUID,
    payload: EmployeeAllocationCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> EmployeeAllocationRead:
    if payload.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="project_id do corpo deve coincidir com a URL.")
    data = payload.model_dump()
    sc = parse_scenario(data.get("scenario"), default=default_scenario_for_create(actor))
    await assert_may_write_scenario(user=actor, scenario=sc, db=db, project_id=project_id)
    data["scenario"] = sc
    row = await EmployeesService(db).create_allocation(
        actor_user_id=actor.id, data=data, actor=actor, request=request
    )
    return EmployeeAllocationRead.model_validate(row)


@router.get("/{project_id}", response_model=ProjectRead, dependencies=[Depends(require_permission(PROJECTS_VIEW))])
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> ProjectRead:
    proj = await ProjectsService(db).get_project(project_id)
    return ProjectRead.model_validate(proj)


@router.post("/", response_model=ProjectRead, dependencies=[Depends(require_permission(PROJECTS_CREATE))])
async def create_project(
    payload: ProjectCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> ProjectRead:
    proj = await ProjectsService(db).create_project(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    return ProjectRead.model_validate(proj)


@router.patch("/{project_id}", response_model=ProjectRead, dependencies=[Depends(require_permission(PROJECTS_EDIT))])
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectRead:
    proj = await ProjectsService(db).update_project(
        actor_user_id=actor.id,
        project_id=project_id,
        data=payload.model_dump(),
        actor=actor,
        request=request,
    )
    return ProjectRead.model_validate(proj)


@router.delete("/{project_id}", status_code=204, dependencies=[Depends(require_permission(PROJECTS_DELETE))])
async def delete_project(
    project_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> None:
    await ProjectsService(db).delete_project(
        actor_user_id=actor.id, project_id=project_id, actor=actor, request=request
    )


@router.post("/{project_id}/users/{user_id}", status_code=204, dependencies=[Depends(require_permission(USERS_MANAGE))])
async def add_user_to_project(
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_project_access),
) -> None:
    link = ProjectUser(project_id=project_id, user_id=user_id, access_level="member")
    db.add(link)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Usuário já vinculado ao projeto.")
