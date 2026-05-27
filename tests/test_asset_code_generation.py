"""Geração e apresentação de códigos patrimoniais (ME- / ASSET-)."""

from app.services.assets_service import (
    _format_asset_code,
    _max_asset_code_sequence,
    present_asset_code,
)


def test_present_asset_code_maps_legacy_asset_prefix() -> None:
    assert present_asset_code("ASSET-00003") == "ME-00003"
    assert present_asset_code("me-00003") == "ME-00003"


def test_max_sequence_across_mixed_prefixes() -> None:
    codes = ["ASSET-00005", "ME-00003", "ME-00010", "OTHER-999", ""]
    assert _max_asset_code_sequence(codes) == 10


def test_next_code_after_legacy_max() -> None:
    assert _format_asset_code(_max_asset_code_sequence(["ASSET-00005"]) + 1) == "ME-00006"


def test_next_code_after_me_max() -> None:
    assert _format_asset_code(_max_asset_code_sequence(["ME-00007", "ASSET-00001"]) + 1) == "ME-00008"
