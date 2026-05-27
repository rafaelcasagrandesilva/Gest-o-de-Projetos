"""Separação lógica EPI vs patrimônio (sem migration)."""

from app.services.asset_categories import (
    MACRO_CATEGORY_EPI,
    categories_for_scope,
    epi_category_db_values,
    is_epi_category,
)


def test_is_epi_category_normalizes_legacy() -> None:
    assert is_epi_category("EPI")
    assert is_epi_category("EPIS")
    assert is_epi_category("epi")
    assert not is_epi_category("Tecnologia")
    assert not is_epi_category("Ferramenta")


def test_categories_for_scope() -> None:
    assert MACRO_CATEGORY_EPI not in categories_for_scope("patrimonial")
    assert categories_for_scope("epi") == [MACRO_CATEGORY_EPI]
    assert MACRO_CATEGORY_EPI in categories_for_scope("all")


def test_epi_db_values_include_legacy() -> None:
    vals = epi_category_db_values()
    assert "EPI" in vals
    assert "EPIS" in vals


def test_patrimonial_scope_has_tecnologia_not_epi() -> None:
    pat = categories_for_scope("patrimonial")
    assert "Tecnologia" in pat
    assert "EPI" not in pat
