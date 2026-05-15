from __future__ import annotations

from unittest.mock import MagicMock

from max.exports import build_customer_reference_readiness_export
from max.exports.customer_reference_readiness import render_customer_reference_readiness_markdown


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


def test_readiness_score_tiers_and_evidence() -> None:
    report = build_customer_reference_readiness_export(_store([
        _unit("ready", {"customer": "Acme", "adoption": "high", "satisfaction": "promoter", "renewal_status": "renewed", "strategic_fit": "strategic", "support_burden": "none", "evidence": ["nps"]}),
        _unit("blocked", {"customer": "Beta", "adoption": "high", "open_escalations": "open sev1"}),
    ]))

    assert [row["idea_id"] for row in report["candidates"]] == ["ready", "blocked"]
    assert report["candidates"][0]["candidate_tier"] == "tier_1"
    assert report["candidates"][0]["supporting_evidence"]
    assert report["candidates"][1]["candidate_tier"] == "not_ready"
    assert "Open escalations" in report["candidates"][1]["disqualifiers"]


def test_empty_and_markdown_output() -> None:
    report = build_customer_reference_readiness_export(_store([]))

    assert report["summary"]["candidate_count"] == 0
    assert "No customer candidates" in render_customer_reference_readiness_markdown(report)
