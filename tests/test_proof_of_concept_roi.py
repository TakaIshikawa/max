from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_proof_of_concept_roi_export
from max.exports.proof_of_concept_roi import (
    render_proof_of_concept_roi_json,
    render_proof_of_concept_roi_markdown,
)


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = metadata.get("title", unit_id)
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_poc_roi_report_sorts_high_risk_and_summarizes_value() -> None:
    report = build_proof_of_concept_roi_export(_store([
        _unit("low", {"account": "Acme", "expected_revenue": "120000", "poc_investment": "20000", "labor_cost": 5000, "success_metrics": ["activation: 80%", "time saved"], "confidence": "high", "owner": "SE"}),
        _unit("high", {"account": "Beta", "expected_revenue": "10000", "poc_investment": "30000", "risk_flags": ["security review blocked"], "success_metrics": "admin adoption: 10 users"}),
    ]))

    assert [row["idea_id"] for row in report["roi_rows"]] == ["high", "low"]
    assert report["roi_rows"][0]["risk_level"] == "high"
    assert report["roi_rows"][0]["roi_summary"]["net_value"] == -20000
    assert report["roi_rows"][1]["roi_summary"]["roi_percent"] == 380.0
    assert report["summary"]["total_expected_value"] == 130000
    assert report["summary"]["high_risk_count"] == 1
    assert report["risk_flags"][0]["flag"] == "security review blocked"


def test_poc_roi_report_handles_missing_optional_fields() -> None:
    report = build_proof_of_concept_roi_export(_store([_unit("empty", {})]), domain="sales")
    row = report["roi_rows"][0]

    assert row["account"] == "Unknown"
    assert row["roi_summary"]["total_cost"] == 0
    assert row["success_metrics"] == []
    assert row["risk_level"] == "medium"
    assert {flag["flag"] for flag in row["risk_flags"]} == {"missing investment estimate", "missing success metrics"}
    assert report["source"]["domain_filter"] == "sales"


def test_poc_roi_renderers_are_json_serializable_and_markdown_handles_empty() -> None:
    report = build_proof_of_concept_roi_export(_store([]))

    assert json.loads(render_proof_of_concept_roi_json(report))["roi_rows"] == []
    markdown = render_proof_of_concept_roi_markdown(report)
    assert "Proof-of-Concept ROI Report" in markdown
    assert "No proof-of-concept ROI metadata" in markdown
