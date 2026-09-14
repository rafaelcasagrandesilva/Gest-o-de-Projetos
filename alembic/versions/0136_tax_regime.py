"""Regime tributário da empresa (Lucro Presumido × Lucro Real) com vigências.

1. `system_settings` ganha os parâmetros dos dois regimes (frações 0–1, exceto o limite mensal
   do adicional de IRPJ, que é dinheiro):
   - ISS (comum);
   - Lucro Presumido: PIS, COFINS, presunção de IRPJ e de CSLL;
   - IRPJ, adicional de IRPJ (+ limite mensal) e CSLL (comuns);
   - Lucro Real: PIS, COFINS e créditos estimados de PIS/COFINS (% da receita).
   `tax_rate` continua existindo e passa a ser só a RESERVA dos meses sem regime cadastrado.
2. Nova tabela `tax_regime_periods`: cada linha informa a data em que um regime passa a valer
   ("data de realização da mudança"), aplicada por competência. Meses anteriores continuam no
   regime antigo.
3. Carga inicial: um período LUCRO_PRESUMIDO a partir de 01/01/2020 (informado pelo contador),
   ajustável na tela de Configurações.

Exclusivamente ADITIVA — nenhuma coluna ou tabela existente é alterada.

Revision ID: 0136_tax_regime
Revises: 0135_remove_advance_fee_payables
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0136_tax_regime"
down_revision = "0135_remove_advance_fee_payables"
branch_labels = None
depends_on = None

# (coluna, default) — todas Numeric(8, 6) NOT NULL.
_RATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("iss_rate", "0.050000"),
    ("pis_presumido_rate", "0.006500"),
    ("cofins_presumido_rate", "0.030000"),
    ("irpj_presumption_rate", "0.320000"),
    ("csll_presumption_rate", "0.320000"),
    ("irpj_rate", "0.150000"),
    ("irpj_additional_rate", "0.100000"),
    ("csll_rate", "0.090000"),
    ("pis_real_rate", "0.016500"),
    ("cofins_real_rate", "0.076000"),
    ("pis_cofins_credit_rate", "0.000000"),
)


def upgrade() -> None:
    for name, default in _RATE_COLUMNS:
        op.add_column(
            "system_settings",
            sa.Column(name, sa.Numeric(8, 6), nullable=False, server_default=default),
        )
    op.add_column(
        "system_settings",
        sa.Column(
            "irpj_additional_monthly_threshold",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="20000.00",
        ),
    )

    table = op.create_table(
        "tax_regime_periods",
        # id e timestamps vêm da aplicação (TimestampUUIDMixin), como nas demais tabelas.
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("regime", sa.String(20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("start_date", name="uq_tax_regime_periods_start_date"),
        sa.CheckConstraint(
            "regime IN ('LUCRO_PRESUMIDO', 'LUCRO_REAL')",
            name="ck_tax_regime_periods_regime",
        ),
    )

    now = datetime.now(timezone.utc)
    op.bulk_insert(
        table,
        [
            {
                "id": uuid.uuid4(),
                "regime": "LUCRO_PRESUMIDO",
                "start_date": date(2020, 1, 1),
                "note": "Regime informado pelo contador (carga inicial) — ajuste a data se necessário",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("tax_regime_periods")
    op.drop_column("system_settings", "irpj_additional_monthly_threshold")
    for name, _default in reversed(_RATE_COLUMNS):
        op.drop_column("system_settings", name)
