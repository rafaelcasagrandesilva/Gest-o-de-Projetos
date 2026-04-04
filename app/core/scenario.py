from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import cast, literal
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.sql.elements import ColumnElement


class Scenario(str, Enum):
    PREVISTO = "PREVISTO"
    REALIZADO = "REALIZADO"


# Aliases para type hints / API
ScenarioKind = Scenario
ScenarioEnum = Scenario

DEFAULT_SCENARIO = Scenario.REALIZADO.value


def _scenario_db_values(enum_cls: type[Scenario]) -> list[str]:
    return [m.value for m in enum_cls]


# Alinhado ao ENUM PostgreSQL `scenario_kind` (criado nas migrations; não recriar via metadata)
SCENARIO_KIND_DB = PG_ENUM(
    Scenario,
    name="scenario_kind",
    create_type=False,
    values_callable=_scenario_db_values,
)


def coerce_scenario(value: Scenario | str | None) -> Scenario:
    """Normaliza para enum Python (queries contra colunas scenario_kind no PG)."""
    if isinstance(value, Scenario):
        return value
    return get_effective_scenario(value)


def scenario_pg_rhs(scenario: Scenario | str | None) -> ColumnElement[Any]:
    """Expressão SQL para `coluna.scenario == …` no PostgreSQL (CAST explícito para `scenario_kind`, evita bind VARCHAR)."""
    s = coerce_scenario(scenario)
    return cast(literal(s.value), SCENARIO_KIND_DB)


def get_effective_scenario(scenario: str | None) -> ScenarioKind:
    """Cenário efetivo para leitura/consulta: nunca None; inválido → REALIZADO."""
    if scenario is None:
        return ScenarioKind.REALIZADO
    s = str(scenario).strip()
    if not s:
        return ScenarioKind.REALIZADO
    try:
        return ScenarioKind(s.upper())
    except ValueError:
        return ScenarioKind.REALIZADO


def parse_scenario(value: str | None, *, default: str = DEFAULT_SCENARIO) -> str:
    """Normaliza cenário em payloads: ausente/vazio → default; inválido → default (ex.: default_scenario_for_create)."""
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return default
    s = str(value).strip().upper()
    if s in (Scenario.PREVISTO.value, Scenario.REALIZADO.value):
        return s
    return default
