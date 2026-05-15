from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_customer_journey_friction_report_export
from max.exports.customer_journey_friction_report import (
    KIND,
    SCHEMA_VERSION,
    render_customer_journey_friction_report_json,
    render_customer_journey_friction_report_markdown,
)


def _unit(unit_id: str, title: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_empty_input_returns_well_formed_report() -> None:
    report = build_customer_journey_friction_report_export(_store([]), domain="cs")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["friction_point_count"] == 0
    assert report["summary"]["severity_counts"] == {"critical": 0, "high": 0, "medium": 0, "low": 0}
    assert report["stages"] == []
    assert "No lifecycle evidence found" in render_customer_journey_friction_report_markdown(report)


def test_groups_friction_points_by_lifecycle_stage_with_evidence() -> None:
    report = build_customer_journey_friction_report_export(
        _store([
            _unit("a", "Slow SSO", {"stage": "onboarding", "severity": "high", "evidence": ["ticket-1"], "drivers": ["SSO setup"]}),
            _unit("b", "Low Usage", {"stage": "adoption", "impact": "moderate usage drop", "evidence_references": ["usage-7"]}),
            _unit("c", "Training Gap", {"stage": "implementation", "severity": "low"}),
        ])
    )

    assert [stage["stage"] for stage in report["stages"]] == ["onboarding", "adoption"]
    onboarding = report["stages"][0]
    assert onboarding["friction_point_count"] == 2
    assert onboarding["highest_severity"] == "high"
    assert onboarding["friction_points"][0]["evidence_references"] == ["ticket-1"]


def test_severity_scoring_orders_critical_high_medium_low() -> None:
    report = build_customer_journey_friction_report_export(
        _store([
            _unit("low", "Low", {"stage": "support", "severity": "low"}),
            _unit("critical", "Critical", {"stage": "support", "severity": "critical escalation", "evidence": ["case", "slack"]}),
            _unit("medium", "Medium", {"stage": "support", "severity": "medium"}),
            _unit("high", "High", {"stage": "support", "severity_score": 75}),
        ])
    )

    stage_points = report["stages"][0]["friction_points"]
    assert [point["idea_id"] for point in stage_points] == ["critical", "high", "medium", "low"]
    assert [point["severity"] for point in stage_points] == ["critical", "high", "medium", "low"]


def test_markdown_and_json_outputs_are_parseable_and_stable() -> None:
    report = build_customer_journey_friction_report_export(
        _store([_unit("a", "Renewal Risk", {"stage": "renewal", "support_load": "many open escalations"})])
    )

    markdown = render_customer_journey_friction_report_markdown(report)
    rendered_json = render_customer_journey_friction_report_json(report)

    assert "# Customer Journey Friction Report" in markdown
    assert "## Lifecycle Stages" in markdown
    assert markdown.endswith("\n")
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rendered_json == render_customer_journey_friction_report_json(report)
