from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ROLE_ADMIN,
    ROLE_CONSULTA,
    ROLE_GESTOR,
    ensure_project_access,
    get_current_user,
    require_admin,
    require_roles,
)
from app.database.session import get_db
from app.models.user import User
from app.schemas.fleet import VehicleCreate, VehicleRead, VehicleUpdate, VehicleUsageCreate, VehicleUsageRead
from app.services.fleet_service import FleetService, fleet_vehicle_to_read


_read = [Depends(require_roles(ROLE_ADMIN, ROLE_GESTOR, ROLE_CONSULTA))]

router = APIRouter()


@router.get("", response_model=list[VehicleRead], dependencies=_read)
async def list_vehicles(
    db: AsyncSession = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    active_only: bool = Query(default=False, description="Somente veículos ativos (para alocação em projetos)"),
) -> list[VehicleRead]:
    rows = await FleetService(db).list_vehicles(offset=offset, limit=limit, active_only=active_only)
    return [fleet_vehicle_to_read(r) for r in rows]


@router.post("", response_model=VehicleRead, dependencies=[Depends(require_admin)])
async def create_vehicle(
    payload: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> VehicleRead:
    row = await FleetService(db).create_vehicle(actor_user_id=actor.id, data=payload.model_dump())
    return fleet_vehicle_to_read(row)


@router.patch("/{vehicle_id}", response_model=VehicleRead, dependencies=[Depends(require_admin)])
async def update_vehicle(
    vehicle_id: UUID,
    payload: VehicleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> VehicleRead:
    row = await FleetService(db).update_vehicle(
        actor_user_id=actor.id, vehicle_id=vehicle_id, data=payload.model_dump(exclude_unset=True)
    )
    return fleet_vehicle_to_read(row)


@router.delete("/{vehicle_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_vehicle(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    """Inativa o veículo (is_active=False); não remove o registro nem vínculos por ID."""
    await FleetService(db).delete_vehicle(actor_user_id=actor.id, vehicle_id=vehicle_id)


@router.post("/usages", response_model=VehicleUsageRead, dependencies=_read)
async def create_usage(
    payload: VehicleUsageCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> VehicleUsageRead:
    await ensure_project_access(user=actor, project_id=payload.project_id, db=db)
    row = await FleetService(db).create_usage(actor_user_id=actor.id, data=payload.model_dump())
    return VehicleUsageRead.model_validate(row)
