from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_enterprise_pilot_success_scorecard_export
from max.exports.enterprise_pilot_success_scorecard import (
    render_enterprise_pilot_success_scorecard_json,
    render_enterprise_pilot_success_scorecard_markdown,
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


def test_pilot_scorecard_sorts_lowest_health_then_target_date() -> None:
    report = build_enterprise_pilot_success_scorecard_export(_store([
        _unit("green", {"pilot_goal": "Expand usage", "success_metrics": ["weekly active users"], "usage_progress": 90, "stakeholder_engagement": "strong", "security_status": "approved", "target_close_date": "2026-09-01", "owner": "CSM"}),
        _unit("red-b", {"usage_progress": 20, "stakeholder_engagement": "weak", "technical_blockers": ["SSO"], "security_status": "blocked", "target_close_date": "2026-08-01"}),
        _unit("red-a", {"usage_progress": 20, "stakeholder_engagement": "weak", "technical_blockers": ["DPA"], "security_status": "blocked", "target_close_date": "2026-07-01"}),
    ]))

    assert [row["idea_id"] for row in report["pilot_rows"]] == ["red-a", "red-b", "green"]
    assert report["pilot_rows"][0]["health_label"] == "red"
    assert report["pilot_rows"][-1]["health_label"] == "green"
    assert report["health_distribution"]["red"] == 2
    assert report["summary"]["blocked_pilot_count"] == 2


def test_pilot_scorecard_renderers_handle_empty_store() -> None:
    report = build_enterprise_pilot_success_scorecard_export(_store([]))

    assert json.loads(render_enterprise_pilot_success_scorecard_json(report))["pilot_rows"] == []
    markdown = render_enterprise_pilot_success_scorecard_markdown(report)
    assert "Enterprise Pilot Success Scorecard" in markdown
    assert "No enterprise pilot metadata" in markdown
