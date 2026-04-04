from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.scenario import Scenario, coerce_scenario

if TYPE_CHECKING:
    from app.models.settings import SystemSettings


def compute_vehicle_monthly_cost(
    *,
    settings: SystemSettings,
    vehicle_type: str,
    fuel_type: str,
    km_per_month: float,
    fixed_monthly_cost: float,
) -> float:
    """Custo mensal = custo fixo cadastrado no veículo (frota) + combustível a partir de km e consumo por tipo."""
    cons = {
        "LIGHT": float(settings.consumption_light or 0),
        "PICKUP": float(settings.consumption_pickup or 0),
        "SEDAN": float(settings.consumption_sedan or 0),
    }
    fuel_p = {
        "ETHANOL": float(settings.fuel_ethanol or 0),
        "GASOLINE": float(settings.fuel_gasoline or 0),
        "DIESEL": float(settings.fuel_diesel or 0),
    }
    fixed = float(fixed_monthly_cost or 0)
    c = cons.get(vehicle_type, 0.0)
    fp = fuel_p.get(fuel_type, 0.0)
    km = float(km_per_month or 0)
    fuel_cost = (km / c) * fp if c > 0 else 0.0
    return fixed + fuel_cost


def compute_project_vehicle_monthly_cost(
    *,
    scenario: Scenario | str,
    settings: "SystemSettings",
    vehicle_type: str,
    fuel_type: str | None,
    km_per_month: float | None,
    fuel_cost_realized: float | None,
    fixed_monthly_cost: float,
) -> float:
    """Custo da alocação no projeto: PREVISTO = fixo + combustível por km; REALIZADO = fixo + combustível informado (sem km/tipo)."""
    sc = coerce_scenario(scenario)
    if sc == Scenario.REALIZADO:
        fixed = float(fixed_monthly_cost or 0)
        fuel = float(fuel_cost_realized) if fuel_cost_realized is not None else 0.0
        return fixed + fuel
    ft = fuel_type or "GASOLINE"
    km = float(km_per_month or 0)
    return compute_vehicle_monthly_cost(
        settings=settings,
        vehicle_type=vehicle_type,
        fuel_type=ft,
        km_per_month=km,
        fixed_monthly_cost=fixed_monthly_cost,
    )


def vehicle_fuel_only_estimate(
    *,
    scenario: Scenario | str,
    settings: "SystemSettings",
    vehicle_type: str,
    fuel_type: str | None,
    km_per_month: float | None,
    fuel_cost_realized: float | None,
    fixed_monthly_cost: float,
) -> float | None:
    """Parcela de combustível para exibição (previsto = estimativa por km; realizado = valor informado)."""
    sc = coerce_scenario(scenario)
    if sc == Scenario.REALIZADO:
        return float(fuel_cost_realized) if fuel_cost_realized is not None else None
    total = compute_project_vehicle_monthly_cost(
        scenario=sc,
        settings=settings,
        vehicle_type=vehicle_type,
        fuel_type=fuel_type,
        km_per_month=km_per_month,
        fuel_cost_realized=fuel_cost_realized,
        fixed_monthly_cost=fixed_monthly_cost,
    )
    fixed = float(fixed_monthly_cost or 0)
    return max(0.0, float(total) - fixed)


def fuel_cost_per_km_realized(fuel_cost_realized: float | None, km_per_month: float | None) -> float | None:
    if fuel_cost_realized is None or km_per_month is None:
        return None
    km = float(km_per_month)
    if km <= 0:
        return None
    return float(fuel_cost_realized) / km
