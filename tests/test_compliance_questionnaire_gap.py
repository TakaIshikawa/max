from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_compliance_questionnaire_gap_export
from max.exports.compliance_questionnaire_gap import (
    render_compliance_questionnaire_gap_json,
    render_compliance_questionnaire_gap_markdown,
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


def test_compliance_gap_orders_missing_requirements_and_scores_readiness() -> None:
    report = build_compliance_questionnaire_gap_export(_store([
        _unit("ready", {"requirement": "Encryption", "required_evidence": ["SOC2", "KMS policy"], "available_evidence": ["SOC2", "KMS policy"], "owner": "GRC"}),
        _unit("partial", {"requirement": "Incident response", "required_evidence": ["IR plan", "tabletop"], "available_evidence": ["IR plan"], "due_date": "2026-07-01"}),
        _unit("missing", {"requirement": "Data retention", "required_evidence": ["retention policy"], "due_date": "2026-06-01"}),
    ]))

    assert [row["idea_id"] for row in report["gap_rows"]] == ["missing", "partial", "ready"]
    assert report["gap_rows"][0]["response_readiness"] == "missing"
    assert report["gap_rows"][1]["readiness_score"] == 50
    assert report["gap_rows"][2]["readiness_score"] == 100
    assert report["summary"]["missing_evidence_count"] == 2
    assert report["missing_evidence"][0]["artifact"] == "retention policy"


def test_compliance_gap_handles_empty_optional_fields() -> None:
    report = build_compliance_questionnaire_gap_export(_store([_unit("empty", {})]), domain="security")
    row = report["gap_rows"][0]

    assert row["requirement"] == "empty"
    assert row["requirement_coverage"]["required_artifacts"] == []
    assert row["missing_evidence"] == []
    assert row["response_readiness"] == "missing"
    assert row["next_action"] == "Unassigned to define required evidence."
    assert report["source"]["domain_filter"] == "security"


def test_compliance_gap_renderers_are_json_serializable() -> None:
    report = build_compliance_questionnaire_gap_export(_store([]))

    assert json.loads(render_compliance_questionnaire_gap_json(report))["gap_rows"] == []
    markdown = render_compliance_questionnaire_gap_markdown(report)
    assert "Compliance Questionnaire Gap Analysis" in markdown
    assert "No compliance questionnaire gap metadata" in markdown
