from __future__ import annotations

from typing import TYPE_CHECKING

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
