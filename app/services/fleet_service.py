from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fleet import Vehicle, VehicleUsage
from app.models.user import User
from app.models.project_operational import ProjectVehicle
from app.repositories.fleet import VehicleRepository, VehicleUsageRepository
from app.schemas.fleet import VehicleRead
from app.services.audit_service import AuditService
from app.services.operational_cost_calc import compute_project_vehicle_monthly_cost
from app.services.settings_service import SettingsService
from app.services.utils import model_to_dict
from app.utils.lifecycle import normalize_lifecycle


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
        cost_center=getattr(v, "cost_center", None),
        is_active=bool(v.is_active),
        start_date=getattr(v, "start_date", None),
        end_date=getattr(v, "end_date", None),
    )


class FleetService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.vehicles = VehicleRepository(session)
        self.usages = VehicleUsageRepository(session)
        self.audit = AuditService(session)

    async def list_vehicles(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        include_inactive: bool = False,
        cost_center: str | None = None,
        competence=None,
        cost_center_exact: str | None = None,
    ) -> list[Vehicle]:
        return await self.vehicles.list_ordered(
            offset=offset,
            limit=limit,
            include_inactive=include_inactive,
            cost_center=cost_center,
            competence=competence,
            cost_center_exact=cost_center_exact,
        )

    async def list_active_for_project(
        self, *, project_id, competencia, offset: int = 0, limit: int = 500
    ) -> list[Vehicle]:
        """Veículos ATIVOS elegíveis para o projeto na competência: Centro de Custo VIGENTE
        igual ao do projeto OU sem centro. Sem project_id → todos (compat)."""
        from app.services.employees_service import EmployeesService

        cc = None
        if project_id is not None:
            cc = await EmployeesService(self.session).cost_center_for_project(project_id)
        return await self.vehicles.list_ordered(
            offset=offset, limit=limit, include_inactive=False, cost_center=cc, competence=competencia
        )

    async def get_vehicle(self, vehicle_id) -> Vehicle:
        v = await self.vehicles.get(vehicle_id)
        if not v or getattr(v, "deleted_at", None) is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Veículo não encontrado.")
        return v

    async def assert_vehicle_valid_for_new_usage(self, *, vehicle_id) -> Vehicle:
        v = await self.vehicles.get(vehicle_id)
        if not v or getattr(v, "deleted_at", None) is not None or not bool(getattr(v, "is_active", False)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Veículo inválido")
        return v

    async def create_vehicle(
        self,
        *,
        actor_user_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> Vehicle:
        if "plate" in data and data.get("plate") is not None:
            data["plate"] = str(data["plate"]).strip().upper()
        try:
            data["end_date"] = normalize_lifecycle(
                is_active=bool(data.get("is_active", True)), end_date=data.get("end_date")
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        # `cost_center_effective_date` não é coluna do veículo (só usado na edição).
        data.pop("cost_center_effective_date", None)
        v = Vehicle(**data)
        await self.vehicles.add(v)
        # Histórico inicial (fonte da verdade temporal) refletindo o centro do cadastro.
        from app.services.cost_center_history_service import VehicleCostCenterService

        await VehicleCostCenterService(self.session).ensure_initial_history(v)
        await self.audit.log_action(
            user=actor,
            action="create",
            entity="vehicle",
            entity_id=v.id,
            before=None,
            after=model_to_dict(v),
            context={"descricao": "Cadastro de veículo"},
            request=request,
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

    async def update_vehicle(
        self,
        *,
        actor_user_id,
        vehicle_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> Vehicle:
        v = await self.get_vehicle(vehicle_id)
        before = model_to_dict(v)
        if "plate" in data and data.get("plate") is not None:
            data["plate"] = str(data["plate"]).strip().upper()
        # Centro de Custo é TEMPORAL: não setar direto o cache; roteia pelo histórico.
        cc_touched = "cost_center" in data
        new_cc = data.pop("cost_center", None)
        cc_effective = data.pop("cost_center_effective_date", None)
        for key, value in data.items():
            setattr(v, key, value)
        if cc_touched:
            from app.services.cost_center_history_service import VehicleCostCenterService
            from app.services.employees_service import default_cost_reference

            await VehicleCostCenterService(self.session).change_cost_center(
                v, new_cc, cc_effective or default_cost_reference()
            )
        # Invariante do ciclo de vida (só quando status/encerramento é tocado, para não
        # bloquear edições não relacionadas): inativo exige end_date; ativo limpa-o.
        if "is_active" in data or "end_date" in data:
            try:
                v.end_date = normalize_lifecycle(is_active=bool(v.is_active), end_date=v.end_date)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        await self.audit.log_action(
            user=actor,
            action="update",
            entity="vehicle",
            entity_id=v.id,
            before=before,
            after=model_to_dict(v),
            context={"descricao": "Atualização de veículo"},
            request=request,
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

    async def delete_vehicle(
        self,
        *,
        actor_user_id,
        vehicle_id,
        actor: User | None = None,
        request: Request | None = None,
    ) -> None:
        v = await self.get_vehicle(vehicle_id)
        before = model_to_dict(v)
        v.is_active = False
        v.deleted_at = datetime.now(timezone.utc)
        await self.audit.log_action(
            user=actor,
            action="update",
            entity="vehicle",
            entity_id=vehicle_id,
            before=before,
            after=model_to_dict(v),
            context={"descricao": "Exclusão (soft delete) de veículo"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(v)

    async def create_usage(
        self,
        *,
        actor_user_id,
        data: dict,
        actor: User | None = None,
        request: Request | None = None,
    ) -> VehicleUsage:
        await self.assert_vehicle_valid_for_new_usage(vehicle_id=data.get("vehicle_id"))
        usage = VehicleUsage(**data)
        await self.usages.add(usage)
        await self.audit.log_action(
            user=actor,
            action="create",
            entity="vehicle_usage",
            entity_id=usage.id,
            before=None,
            after=model_to_dict(usage),
            context={"descricao": "Uso de veículo"},
            request=request,
        )
        await self.session.commit()
        await self.session.refresh(usage)
        return usage

