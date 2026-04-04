"""Verificação defensiva: colunas `scenario` presentes (migrations 0015+)."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

SCENARIO_TABLES = (
    "revenues",
    "employee_allocations",
    "vehicle_usages",
    "project_fixed_costs",
    "project_labors",
    "project_vehicles",
    "project_system_costs",
    "project_operational_fixed",
)


async def warn_if_scenario_schema_missing(engine: AsyncEngine) -> None:
    """Em PostgreSQL, avisa se falta coluna scenario (alembic upgrade pendente)."""
    url = str(engine.url)
    if "postgresql" not in url:
        return

    async with engine.connect() as conn:
        for table in SCENARIO_TABLES:
            r = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = :table_name AND column_name = 'scenario'"
                ),
                {"table_name": table},
            )
            if r.fetchone() is None:
                logger.error(
                    "Schema incompleto: tabela '%s' sem coluna 'scenario'. "
                    "Execute: alembic upgrade head (revisões 0015_previsto_realizado e 0016_scenario_columns_ensure).",
                    table,
                )
