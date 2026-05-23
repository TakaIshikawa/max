from __future__ import annotations

from unittest.mock import MagicMock

from max.exports import build_feature_entitlement_revenue_leakage_report_export
from max.exports.feature_entitlement_revenue_leakage_report import render_feature_entitlement_revenue_leakage_report_markdown


def test_feature_entitlement_revenue_leakage_identifies_uncontracted_usage() -> None:
    report = build_feature_entitlement_revenue_leakage_report_export(_store([
        _unit("a", {"account": "A", "contracted_features": ["sso"], "entitled_features": ["sso", "audit"], "leakage_amount_usd": 12000}),
        _unit("b", {"account": "B", "contracted_features": ["sso"], "used_features": ["sso"]}),
    ]))

    assert report["summary"]["finding_count"] == 1
    assert report["summary"]["total_leakage_amount_usd"] == 12000
    assert report["account_rows"][0]["severity"] == "medium"
    assert "audit" in render_feature_entitlement_revenue_leakage_report_markdown(report)


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = unit_id
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store
