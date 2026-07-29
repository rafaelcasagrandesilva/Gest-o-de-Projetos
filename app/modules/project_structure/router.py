from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_may_write_scenario,
    default_scenario_for_create,
    get_current_user,
    require_permission,
    require_project_access,
)
from app.core.permission_codes import PROJECTS_UPDATE
from app.core.scenario import coerce_scenario, parse_scenario
from app.api.sensitive import redact_for
from app.database.session import get_db
from app.models.user import User
from app.schemas.project_structure import (
    CategoryCopyResultRead,
    InitializeCompetenciaBody,
    InitializeCompetenciaResult,
    ProjectLaborCopyFromPreviousBody,
    ProjectLaborCopyFromPreviousResult,
    ProjectLaborCostUpdate,
    ProjectLaborCreate,
    ProjectLaborDetailItem,
    ProjectLaborRead,
    ProjectOperationalFixedCreate,
    ProjectOperationalFixedRead,
    ProjectOperationalFixedUpdate,
    ProjectSystemCostCreate,
    ProjectSystemCostRead,
    ProjectSystemCostUpdate,
    ProjectVehicleCreate,
    ProjectVehicleRead,
    ProjectVehicleUpdate,
)
from app.services.competencia_initialization_service import (
    CompetenciaInitializationService,
    CostCategory,
    InitializationOrigin,
)
from app.services.project_structure_service import ProjectStructureService


router = APIRouter()
# Escrita da estrutura do projeto pelo VERBO `projects.update` ("Editar" na grade).
# Migrado do legado `projects.edit` para alinhar com o modelo de verbos: a coluna "Editar"
# concede `projects.update`, e o grafo mantém retrocompat (`projects.edit ⇒ projects.update`),
# então ADMIN (e qualquer um com o legado) continua passando. Espelha o módulo de Componentes
# Variáveis, que já exige `projects.update`.
_write = [Depends(require_permission(PROJECTS_UPDATE))]


def _svc(db: AsyncSession) -> ProjectStructureService:
    return ProjectStructureService(db)


# --- Mão de obra ---


@router.get("/{project_id}/labor-details", response_model=list[ProjectLaborDetailItem])
async def get_project_labor_details(
    project_id: UUID,
    competencia: date = Query(..., description="Primeiro dia do mês"),
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access),
) -> list[ProjectLaborDetailItem]:
    sc = coerce_scenario(scenario_param)
    _rows = await _svc(db).list_labor_details(project_id=project_id, competencia=competencia, scenario=sc)
    return [redact_for("project_labor_detail", _m, user) for _m in _rows]


@router.get("/{project_id}/structure/labors", response_model=list[ProjectLaborRead])
async def list_structure_labors(
    project_id: UUID,
    competencia: date = Query(..., description="Primeiro dia do mês"),
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access),
) -> list[ProjectLaborRead]:
    sc = coerce_scenario(scenario_param)
    _rows = await _svc(db).list_labors_read(project_id=project_id, competencia=competencia, scenario=sc)
    return [redact_for("project_labor", _m, user) for _m in _rows]


@router.post("/{project_id}/structure/labors", response_model=ProjectLaborRead, dependencies=_write)
async def create_structure_labor(
    project_id: UUID,
    payload: ProjectLaborCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectLaborRead:
    data = payload.model_dump()
    sc = parse_scenario(data.get("scenario"), default=default_scenario_for_create(actor))
    await assert_may_write_scenario(user=actor, scenario=sc, db=db, project_id=project_id)
    data["scenario"] = sc
    return redact_for("project_labor", await _svc(db).create_labor(project_id=project_id, data=data, actor=actor, request=request), actor)


@router.post(
    "/{project_id}/structure/labors/copy-from-previous",
    response_model=ProjectLaborCopyFromPreviousResult,
    dependencies=_write,
)
async def copy_structure_labors_from_previous(
    project_id: UUID,
    payload: ProjectLaborCopyFromPreviousBody,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectLaborCopyFromPreviousResult:
    data = payload.model_dump()
    sc = parse_scenario(data.get("scenario"), default=default_scenario_for_create(actor))
    await assert_may_write_scenario(user=actor, scenario=sc, db=db, project_id=project_id)
    return await _svc(db).copy_labors_from_previous_month(
        project_id=project_id, competencia=payload.competencia, scenario=sc
    )


# --- Inicializar Competência (fluxo único reutilizável por todas as abas) ---


@router.post(
    "/{project_id}/structure/initialize-competencia",
    response_model=InitializeCompetenciaResult,
    dependencies=_write,
)
async def initialize_competencia(
    project_id: UUID,
    payload: InitializeCompetenciaBody,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> InitializeCompetenciaResult:
    """Copia (substituindo) as categorias selecionadas de uma origem para a competência.

    O cenário de destino é definido pela origem escolhida (Realizado/Previsto).
    Reutiliza CompetenciaInitializationService (backend centraliza a lógica).
    """
    origin = InitializationOrigin(payload.origin)
    categories = [CostCategory(c) for c in payload.categories]
    # Cenário de destino vem da origem → valida a permissão de escrita nesse cenário.
    await assert_may_write_scenario(
        user=actor, scenario=origin.target_scenario, db=db, project_id=project_id
    )
    outcome = await CompetenciaInitializationService(db).initialize_from_origin(
        project_id=project_id,
        competencia=payload.competencia,
        origin=origin,
        categories=categories,
    )
    return InitializeCompetenciaResult(
        source_competencia=outcome.source.competencia,
        source_scenario=outcome.source.scenario.value,
        target_competencia=outcome.target.competencia,
        target_scenario=outcome.target.scenario.value,
        results=[
            CategoryCopyResultRead(category=r.category.value, label=r.label, copied=r.copied)
            for r in outcome.results
        ],
    )


@router.patch(
    "/{project_id}/structure/labors/{labor_id}",
    response_model=ProjectLaborRead,
    dependencies=_write,
)
async def patch_structure_labor_costs(
    project_id: UUID,
    labor_id: UUID,
    payload: ProjectLaborCostUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectLaborRead:
    row = await _svc(db).labors.get(labor_id)
    if not row or row.project_id != project_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    await assert_may_write_scenario(user=actor, scenario=row.scenario, db=db, project_id=project_id)
    return redact_for("project_labor", await _svc(db).update_labor_costs(
        project_id=project_id, labor_id=labor_id, payload=payload, actor=actor, request=request
    ), actor)


@router.delete("/{project_id}/structure/labors/{labor_id}", status_code=204, dependencies=_write)
async def delete_structure_labor(
    project_id: UUID,
    labor_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> None:
    row = await _svc(db).labors.get(labor_id)
    if not row or row.project_id != project_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    await assert_may_write_scenario(user=actor, scenario=row.scenario, db=db, project_id=project_id)
    await _svc(db).delete_labor(labor_id=labor_id, actor=actor, request=request)


# --- Veículos ---


@router.get("/{project_id}/structure/vehicles", response_model=list[ProjectVehicleRead])
async def list_structure_vehicles(
    project_id: UUID,
    competencia: date = Query(...),
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access),
) -> list[ProjectVehicleRead]:
    sc = coerce_scenario(scenario_param)
    _rows = await _svc(db).list_project_vehicles_read(project_id=project_id, competencia=competencia, scenario=sc)
    return [redact_for("project_vehicle", _m, user) for _m in _rows]


@router.post("/{project_id}/structure/vehicles", response_model=ProjectVehicleRead, dependencies=_write)
async def create_structure_vehicle(
    project_id: UUID,
    payload: ProjectVehicleCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectVehicleRead:
    data = payload.model_dump()
    sc = parse_scenario(data.get("scenario"), default=default_scenario_for_create(actor))
    await assert_may_write_scenario(user=actor, scenario=sc, db=db, project_id=project_id)
    data["scenario"] = sc
    return redact_for("project_vehicle", await _svc(db).create_project_vehicle(project_id=project_id, data=data), actor)


@router.patch("/{project_id}/structure/vehicles/{vehicle_id}", response_model=ProjectVehicleRead, dependencies=_write)
async def update_structure_vehicle(
    project_id: UUID,
    vehicle_id: UUID,
    payload: ProjectVehicleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectVehicleRead:
    row = await _svc(db).vehicles.get(vehicle_id)
    if not row or row.project_id != project_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    await assert_may_write_scenario(user=actor, scenario=row.scenario, db=db, project_id=project_id)
    return redact_for("project_vehicle", await _svc(db).update_project_vehicle(
        allocation_id=vehicle_id, data=payload.model_dump(exclude_unset=True)
    ), actor)


@router.delete("/{project_id}/structure/vehicles/{vehicle_id}", status_code=204, dependencies=_write)
async def delete_structure_vehicle(
    project_id: UUID,
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> None:
    row = await _svc(db).vehicles.get(vehicle_id)
    if not row or row.project_id != project_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    await assert_may_write_scenario(user=actor, scenario=row.scenario, db=db, project_id=project_id)
    await _svc(db).delete_project_vehicle(allocation_id=vehicle_id)


# --- Sistemas ---


@router.get("/{project_id}/structure/systems", response_model=list[ProjectSystemCostRead])
async def list_structure_systems(
    project_id: UUID,
    competencia: date = Query(...),
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access),
) -> list[ProjectSystemCostRead]:
    sc = coerce_scenario(scenario_param)
    rows = await _svc(db).list_systems(project_id=project_id, competencia=competencia, scenario=sc)
    return [redact_for("project_value", ProjectSystemCostRead.model_validate(r), user) for r in rows]


@router.post("/{project_id}/structure/systems", response_model=ProjectSystemCostRead, dependencies=_write)
async def create_structure_system(
    project_id: UUID,
    payload: ProjectSystemCostCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectSystemCostRead:
    data = payload.model_dump()
    sc = parse_scenario(data.get("scenario"), default=default_scenario_for_create(actor))
    await assert_may_write_scenario(user=actor, scenario=sc, db=db, project_id=project_id)
    data["scenario"] = sc
    row = await _svc(db).create_system(project_id=project_id, data=data)
    return redact_for("project_value", ProjectSystemCostRead.model_validate(row), actor)


@router.patch("/{project_id}/structure/systems/{system_id}", response_model=ProjectSystemCostRead, dependencies=_write)
async def update_structure_system(
    project_id: UUID,
    system_id: UUID,
    payload: ProjectSystemCostUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectSystemCostRead:
    row = await _svc(db).systems.get(system_id)
    if not row or row.project_id != project_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    await assert_may_write_scenario(user=actor, scenario=row.scenario, db=db, project_id=project_id)
    row = await _svc(db).update_system(system_id=system_id, data=payload.model_dump(exclude_unset=True))
    return redact_for("project_value", ProjectSystemCostRead.model_validate(row), actor)


@router.delete("/{project_id}/structure/systems/{system_id}", status_code=204, dependencies=_write)
async def delete_structure_system(
    project_id: UUID,
    system_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> None:
    row = await _svc(db).systems.get(system_id)
    if not row or row.project_id != project_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    await assert_may_write_scenario(user=actor, scenario=row.scenario, db=db, project_id=project_id)
    await _svc(db).delete_system(system_id=system_id)


# --- Custos fixos operacionais ---


@router.get("/{project_id}/structure/fixed-operational", response_model=list[ProjectOperationalFixedRead])
async def list_structure_fixed(
    project_id: UUID,
    competencia: date = Query(...),
    scenario_param: str | None = Query(default=None, alias="scenario", description="Omitir = REALIZADO"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access),
) -> list[ProjectOperationalFixedRead]:
    sc = coerce_scenario(scenario_param)
    rows = await _svc(db).list_fixed(project_id=project_id, competencia=competencia, scenario=sc)
    return [redact_for("project_value", ProjectOperationalFixedRead.model_validate(r), user) for r in rows]


@router.post("/{project_id}/structure/fixed-operational", response_model=ProjectOperationalFixedRead, dependencies=_write)
async def create_structure_fixed(
    project_id: UUID,
    payload: ProjectOperationalFixedCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectOperationalFixedRead:
    data = payload.model_dump()
    sc = parse_scenario(data.get("scenario"), default=default_scenario_for_create(actor))
    await assert_may_write_scenario(user=actor, scenario=sc, db=db, project_id=project_id)
    data["scenario"] = sc
    row = await _svc(db).create_fixed(project_id=project_id, data=data)
    return redact_for("project_value", ProjectOperationalFixedRead.model_validate(row), actor)


@router.patch(
    "/{project_id}/structure/fixed-operational/{fixed_id}",
    response_model=ProjectOperationalFixedRead,
    dependencies=_write,
)
async def update_structure_fixed(
    project_id: UUID,
    fixed_id: UUID,
    payload: ProjectOperationalFixedUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> ProjectOperationalFixedRead:
    row = await _svc(db).fixed.get(fixed_id)
    if not row or row.project_id != project_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    await assert_may_write_scenario(user=actor, scenario=row.scenario, db=db, project_id=project_id)
    row = await _svc(db).update_fixed(fixed_id=fixed_id, data=payload.model_dump(exclude_unset=True))
    return redact_for("project_value", ProjectOperationalFixedRead.model_validate(row), actor)


@router.delete("/{project_id}/structure/fixed-operational/{fixed_id}", status_code=204, dependencies=_write)
async def delete_structure_fixed(
    project_id: UUID,
    fixed_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
    _: User = Depends(require_project_access),
) -> None:
    row = await _svc(db).fixed.get(fixed_id)
    if not row or row.project_id != project_id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado.")
    await assert_may_write_scenario(user=actor, scenario=row.scenario, db=db, project_id=project_id)
    await _svc(db).delete_fixed(fixed_id=fixed_id)
