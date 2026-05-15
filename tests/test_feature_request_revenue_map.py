from __future__ import annotations

from unittest.mock import MagicMock

from max.exports import build_feature_request_revenue_map_export
from max.exports.feature_request_revenue_map import render_feature_request_revenue_map_markdown


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = metadata.get("feature_request", unit_id)
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_duplicate_feature_requests_are_grouped() -> None:
    report = build_feature_request_revenue_map_export(_store([
        _unit("a", {"feature_request": "SCIM provisioning", "account": "Acme", "pipeline_value_usd": 50_000, "urgency": "high", "evidence": ["call"]}),
        _unit("b", {"feature_request": "scim provisioning", "account": "Beta", "retention_risk_usd": 25_000, "evidence": ["ticket", "crm"]}),
    ]))

    assert report["summary"]["feature_request_count"] == 1
    row = report["feature_requests"][0]
    assert row["account_count"] == 2
    assert row["pipeline_value_usd"] == 75_000
    assert row["evidence_strength"] == "strong"


def test_ranking_prefers_revenue_accounts_urgency_and_evidence() -> None:
    report = build_feature_request_revenue_map_export(_store([
        _unit("low", {"feature_request": "Low", "pipeline_value_usd": 10_000}),
        _unit("top", {"feature_request": "Top", "pipeline_value_usd": 100_000, "account": "Acme", "urgency": "critical", "evidence": ["a", "b"]}),
    ]))

    assert report["feature_requests"][0]["feature_request"] == "Top"
    assert report["feature_requests"][0]["rank"] == 1
    assert "Feature Request Revenue Map" in render_feature_request_revenue_map_markdown(report)
