from __future__ import annotations

from datetime import date

from sqlalchemy import CheckConstraint, Date, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin

TAX_REGIMES = ("LUCRO_PRESUMIDO", "LUCRO_REAL")


class TaxRegimePeriod(TimestampUUIDMixin, Base):
    """Vigência do regime tributário da empresa.

    Cada linha diz "a partir de `start_date` (1º dia da competência) o regime é `regime`",
    até a próxima linha. Meses anteriores ao primeiro período usam `SystemSettings.tax_rate`.
    """

    __tablename__ = "tax_regime_periods"
    __table_args__ = (
        UniqueConstraint("start_date", name="uq_tax_regime_periods_start_date"),
        CheckConstraint(
            "regime IN ('LUCRO_PRESUMIDO', 'LUCRO_REAL')",
            name="ck_tax_regime_periods_regime",
        ),
    )

    regime: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
