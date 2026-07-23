from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_may_write_scenario,
    default_scenario_for_create,
    ensure_project_access,
    get_current_user,
    require_permission,
    user_has_permission,
)
from app.api.sensitive import VEHICLE_SENSITIVE_FIELDS, redact
from app.core.permission_codes import (
    VEHICLES_CREATE,
    VEHICLES_SENSITIVE,
    VEHICLES_DELETE,
    VEHICLES_LIST,
    VEHICLES_UPDATE,
)
from app.core.scenario import parse_scenario
from app.database.session import get_db
from app.models.user import User
from app.schemas.fleet import VehicleCreate, VehicleRead, VehicleUpdate, VehicleUsageCreate, VehicleUsageRead
from app.services.fleet_service import FleetService, fleet_vehicle_to_read
from app.services.employees_service import default_cost_reference


# Modelo de verbos (Fase 2): listagens exigem vehicles.list; mutações usam create/update/delete.
_list = [Depends(require_permission(VEHICLES_LIST))]

router = APIRouter()


@router.get("", response_model=list[VehicleRead], dependencies=_list)
async def list_vehicles(
    db: AsyncSession = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    include_inactive: bool = Query(default=False, description="Incluir veículos inativos (telas administrativas)"),
    active_only: bool = Query(
        default=False,
        description="LEGADO: Somente veículos ativos. Use /vehicles/active ou include_inactive.",
    ),
    cost_center: str | None = Query(
        default=None,
        description="Filtra a frota por Centro de Custo (igualdade estrita). Omitido = todos.",
    ),
    user: User = Depends(get_current_user),
) -> list[VehicleRead]:
    # Compat: se active_only=true, força não incluir inativos.
    eff_include_inactive = bool(include_inactive)
    if active_only:
        eff_include_inactive = False
    rows = await FleetService(db).list_vehicles(
        offset=offset, limit=limit, include_inactive=eff_include_inactive, cost_center_exact=cost_center
    )
    _inc = user_has_permission(user, VEHICLES_SENSITIVE)
    return [redact(fleet_vehicle_to_read(r), VEHICLE_SENSITIVE_FIELDS, _inc) for r in rows]


@router.get("/active", response_model=list[VehicleRead], dependencies=_list)
async def list_active_vehicles(
    db: AsyncSession = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    project_id: UUID | None = Query(
        default=None,
        description="Filtra por Centro de Custo do projeto (aba Veículos). Omitido = todos.",
    ),
    competencia: date | None = Query(
        default=None,
        description="Competência para resolver o Centro de Custo VIGENTE do veículo (histórico).",
    ),
    user: User = Depends(get_current_user),
) -> list[VehicleRead]:
    if project_id is not None:
        rows = await FleetService(db).list_active_for_project(
            project_id=project_id,
            competencia=competencia or default_cost_reference(),
            offset=offset,
            limit=limit,
        )
    else:
        rows = await FleetService(db).list_vehicles(offset=offset, limit=limit, include_inactive=False)
    _inc = user_has_permission(user, VEHICLES_SENSITIVE)
    return [redact(fleet_vehicle_to_read(r), VEHICLE_SENSITIVE_FIELDS, _inc) for r in rows]


@router.post("", response_model=VehicleRead, dependencies=[Depends(require_permission(VEHICLES_CREATE))])
async def create_vehicle(
    payload: VehicleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> VehicleRead:
    row = await FleetService(db).create_vehicle(
        actor_user_id=actor.id, data=payload.model_dump(), actor=actor, request=request
    )
    # Criar NÃO concede ver: sem vehicles.sensitive, o custo mensal recém-cadastrado volta omitido.
    _inc = user_has_permission(actor, VEHICLES_SENSITIVE)
    return redact(fleet_vehicle_to_read(row), VEHICLE_SENSITIVE_FIELDS, _inc)


@router.patch("/{vehicle_id}", response_model=VehicleRead, dependencies=[Depends(require_permission(VEHICLES_UPDATE))])
async def update_vehicle(
    vehicle_id: UUID,
    payload: VehicleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> VehicleRead:
    row = await FleetService(db).update_vehicle(
        actor_user_id=actor.id,
        vehicle_id=vehicle_id,
        data=payload.model_dump(exclude_unset=True),
        actor=actor,
        request=request,
    )
    # Editar NÃO concede ver: sem vehicles.sensitive, o custo mensal salvo volta omitido.
    _inc = user_has_permission(actor, VEHICLES_SENSITIVE)
    return redact(fleet_vehicle_to_read(row), VEHICLE_SENSITIVE_FIELDS, _inc)


@router.delete("/{vehicle_id}", status_code=204, dependencies=[Depends(require_permission(VEHICLES_DELETE))])
async def delete_vehicle(
    vehicle_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    """Inativa o veículo (is_active=False); não remove o registro nem vínculos por ID."""
    await FleetService(db).delete_vehicle(
        actor_user_id=actor.id, vehicle_id=vehicle_id, actor=actor, request=request
    )


@router.post("/usages", response_model=VehicleUsageRead, dependencies=[Depends(require_permission(VEHICLES_UPDATE))])
async def create_usage(
    payload: VehicleUsageCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> VehicleUsageRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    data = payload.model_dump()
    sc = parse_scenario(data.get("scenario"), default=default_scenario_for_create(actor))
    await assert_may_write_scenario(
        user=actor, scenario=sc, db=db, project_id=payload.project_id
    )
    data["scenario"] = sc
    row = await FleetService(db).create_usage(
        actor_user_id=actor.id, data=data, actor=actor, request=request
    )
    return VehicleUsageRead.model_validate(row)
