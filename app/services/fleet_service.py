from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fleet import Vehicle, VehicleUsage
from app.models.project_operational import ProjectVehicle
from app.repositories.fleet import VehicleRepository, VehicleUsageRepository
from app.schemas.fleet import VehicleRead
from app.services.audit_service import AuditService
from app.services.operational_cost_calc import compute_project_vehicle_monthly_cost
from app.services.settings_service import SettingsService
from app.services.utils import model_to_dict


def fleet_vehicle_to_read(v: Vehicle) -> VehicleRead:
    """Monta o schema explicitamente (driver_name, aliases JSON) sem depender do model_validate no ORM."""
    drv = v.driver
    driver_name = drv.full_name if drv is not None else None
    vtype = getattr(v, "vehicle_type", None) or "LIGHT"
    return VehicleRead(
        id=v.id,
        created_at=v.created_at,
        updated_at=v.updated_at,
        plate=v.plate,
        model=v.model,
        description=v.description,
        vehicle_type=str(vtype),
        monthly_cost=float(getattr(v, "monthly_cost", 0) or 0),
        driver_employee_id=v.driver_employee_id,
        driver_name=driver_name,
        is_active=bool(v.is_active),
    )


class FleetService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.vehicles = VehicleRepository(session)
        self.usages = VehicleUsageRepository(session)
        self.audit = AuditService(session)

    async def list_vehicles(
        self, *, offset: int = 0, limit: int = 50, active_only: bool = False
    ) -> list[Vehicle]:
        return await self.vehicles.list_ordered(offset=offset, limit=limit, active_only=active_only)

    async def get_vehicle(self, vehicle_id) -> Vehicle:
        v = await self.vehicles.get(vehicle_id)
        if not v:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Veículo não encontrado.")
        return v

    async def create_vehicle(self, *, actor_user_id, data: dict) -> Vehicle:
        if "plate" in data and data.get("plate") is not None:
            data["plate"] = str(data["plate"]).strip().upper()
        v = Vehicle(**data)
        await self.vehicles.add(v)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="Vehicle",
            entity_id=v.id,
            before=None,
            after=model_to_dict(v),
        )
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um veículo com esta placa.",
            )
        await self.session.refresh(v)
        return v

    async def update_vehicle(self, *, actor_user_id, vehicle_id, data: dict) -> Vehicle:
        v = await self.get_vehicle(vehicle_id)
        before = model_to_dict(v)
        if "plate" in data and data.get("plate") is not None:
            data["plate"] = str(data["plate"]).strip().upper()
        for key, value in data.items():
            setattr(v, key, value)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="update",
            entity="Vehicle",
            entity_id=v.id,
            before=before,
            after=model_to_dict(v),
        )
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe um veículo com esta placa.",
            )
        await self.session.refresh(v)
        await self._recalculate_project_allocations_for_vehicle(v.id)
        return v

    async def _recalculate_project_allocations_for_vehicle(self, vehicle_id) -> None:
        """Atualiza custo mensal nas alocações de projeto quando o veículo da frota muda."""
        settings = await SettingsService(self.session).get_or_create()
        fv = await self.vehicles.get(vehicle_id)
        if not fv:
            return
        stmt = select(ProjectVehicle).where(ProjectVehicle.vehicle_id == vehicle_id)
        res = await self.session.execute(stmt)
        rows = list(res.scalars().all())
        if not rows:
            return
        for row in rows:
            row.monthly_cost = compute_project_vehicle_monthly_cost(
                scenario=row.scenario,
                settings=settings,
                vehicle_type=fv.vehicle_type,
                fuel_type=row.fuel_type,
                km_per_month=float(row.km_per_month) if row.km_per_month is not None else None,
                fuel_cost_realized=float(row.fuel_cost_realized) if row.fuel_cost_realized is not None else None,
                fixed_monthly_cost=float(fv.monthly_cost),
            )
        await self.session.commit()

    async def delete_vehicle(self, *, actor_user_id, vehicle_id) -> None:
        v = await self.get_vehicle(vehicle_id)
        before = model_to_dict(v)
        v.is_active = False
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="update",
            entity="Vehicle",
            entity_id=vehicle_id,
            before=before,
            after=model_to_dict(v),
        )
        await self.session.commit()
        await self.session.refresh(v)

    async def create_usage(self, *, actor_user_id, data: dict) -> VehicleUsage:
        usage = VehicleUsage(**data)
        await self.usages.add(usage)
        await self.audit.log(
            actor_user_id=actor_user_id,
            action="create",
            entity="VehicleUsage",
            entity_id=usage.id,
            before=None,
            after=model_to_dict(usage),
        )
        await self.session.commit()
        await self.session.refresh(usage)
        return usage

