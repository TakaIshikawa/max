from __future__ import annotations

from unittest.mock import MagicMock

from max.exports import build_implementation_timeline_variance_report_export
from max.exports.implementation_timeline_variance_report import render_implementation_timeline_variance_report_markdown


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


def test_variance_calculations_and_categories_are_deterministic() -> None:
    report = build_implementation_timeline_variance_report_export(_store([
        _unit("late", {"milestone": "Integrations", "planned_date": "2026-01-01", "actual_date": "2026-01-12", "drivers": ["Vendor delay"]}),
        _unit("early", {"milestone": "Kickoff", "planned_duration_days": 10, "actual_duration_days": 8}),
        _unit("risk", {"milestone": "Launch", "planned_date": "2026-02-01"}),
    ]))

    assert [row["idea_id"] for row in report["milestones"]] == ["late", "risk", "early"]
    assert report["milestones"][0]["variance_days"] == 11
    assert report["milestones"][0]["variance_category"] == "late"
    assert report["milestones"][1]["variance_category"] == "at_risk"
    assert report["milestones"][2]["variance_category"] == "early"


def test_empty_and_markdown_output() -> None:
    report = build_implementation_timeline_variance_report_export(_store([]))

    assert report["summary"]["milestone_count"] == 0
    assert "No implementation milestones" in render_implementation_timeline_variance_report_markdown(report)
