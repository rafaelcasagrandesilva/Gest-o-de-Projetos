from __future__ import annotations

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampUUIDMixin


class SystemSettings(TimestampUUIDMixin, Base):
    """Singleton: uma única linha de configuração global."""

    __tablename__ = "system_settings"

    tax_rate: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    overhead_rate: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    anticipation_rate: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)
    # AUTOMATICO: custo de antecipação vem dos borderôs (real do mês / média dos meses pagos).
    # FIXO: usa `anticipation_rate` acima — mantido como "volta" ao percentual fixo.
    anticipation_mode: Mapped[str] = mapped_column(
        String(16), default="AUTOMATICO", server_default="AUTOMATICO", nullable=False
    )
    # Taxa mensal padrão de correção de dívidas NOVAS (0,5% a.m. = 6% ao ano). Não retroage:
    # dívida já cadastrada só corrige se alguém criar uma vigência para ela.
    debt_default_monthly_rate: Mapped[float] = mapped_column(
        Numeric(9, 6), default=0.005, server_default="0.005000", nullable=False
    )
    clt_charges_rate: Mapped[float] = mapped_column(Numeric(8, 6), default=0, nullable=False)

    # --- Regime tributário (ver TaxRegimePeriod e app/services/tax_calc.py) ---------------- #
    # `tax_rate` acima vira RESERVA: só vale nos meses sem nenhum regime cadastrado.
    iss_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0.05, server_default="0.050000", nullable=False
    )
    # Lucro Presumido
    pis_presumido_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0.0065, server_default="0.006500", nullable=False
    )
    cofins_presumido_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0.03, server_default="0.030000", nullable=False
    )
    irpj_presumption_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0.32, server_default="0.320000", nullable=False
    )
    csll_presumption_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0.32, server_default="0.320000", nullable=False
    )
    # Comuns aos dois regimes
    irpj_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0.15, server_default="0.150000", nullable=False
    )
    irpj_additional_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0.10, server_default="0.100000", nullable=False
    )
    irpj_additional_monthly_threshold: Mapped[float] = mapped_column(
        Numeric(14, 2), default=20000, server_default="20000.00", nullable=False
    )
    csll_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0.09, server_default="0.090000", nullable=False
    )
    # Lucro Real
    pis_real_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0.0165, server_default="0.016500", nullable=False
    )
    cofins_real_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0.076, server_default="0.076000", nullable=False
    )
    # Créditos estimados de PIS/COFINS no Lucro Real, como fração da receita.
    pis_cofins_credit_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), default=0, server_default="0.000000", nullable=False
    )

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
