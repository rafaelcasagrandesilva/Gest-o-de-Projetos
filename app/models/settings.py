from __future__ import annotations

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class SystemSettings(TimestampUUIDMixin, Base):
    """Singleton: uma única linha de configuração global."""

    __tablename__ = "system_settings"

    tax_rate: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    overhead_rate: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    anticipation_rate: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    clt_charges_rate: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)

    vehicle_light_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    vehicle_pickup_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    vehicle_sedan_cost: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    vr_value: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)

    fuel_ethanol: Mapped[float] = mapped_column(Numeric(10, 4), default=0, nullable=False)
    fuel_gasoline: Mapped[float] = mapped_column(Numeric(10, 4), default=0, nullable=False)
    fuel_diesel: Mapped[float] = mapped_column(Numeric(10, 4), default=0, nullable=False)

    consumption_light: Mapped[float] = mapped_column(Numeric(10, 4), default=1, nullable=False)
    consumption_pickup: Mapped[float] = mapped_column(Numeric(10, 4), default=1, nullable=False)
    consumption_sedan: Mapped[float] = mapped_column(Numeric(10, 4), default=1, nullable=False)
