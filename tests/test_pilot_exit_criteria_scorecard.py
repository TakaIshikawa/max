from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.pilot_exit_criteria_scorecard import (
    build_pilot_exit_criteria_scorecard_export,
    render_pilot_exit_criteria_scorecard_json,
    render_pilot_exit_criteria_scorecard_markdown,
)


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


def test_pilot_scorecard_classifies_completion_and_sorting() -> None:
    criteria = ["activation", "security", "roi"]
    report = build_pilot_exit_criteria_scorecard_export(
        _store(
            [
                _unit("complete", {"account": "Zenith", "exit_criteria": criteria, "met_criteria": criteria, "adoption_target": 100, "current_adoption": 120, "technical_validation_status": "passed", "commercial_next_step": "convert", "owner": "Mina"}),
                _unit("on_track", {"account": "Beta", "exit_criteria": criteria, "met_criteria": ["activation", "security"], "adoption_target": 100, "current_adoption": 80, "technical_validation_status": "validated"}),
                _unit("at_risk", {"account": "Delta", "exit_criteria": criteria, "met_criteria": ["activation"], "adoption_target": 100, "current_adoption": 30, "technical_validation_status": "pending"}),
                _unit("blocked", {"account": "Acme", "exit_criteria": criteria, "met_criteria": criteria, "adoption_target": 100, "current_adoption": 100, "technical_validation_status": "passed", "blockers": ["legal"]}),
            ]
        )
    )

    assert [row["idea_id"] for row in report["scorecard_rows"]] == ["blocked", "at_risk", "on_track", "complete"]
    assert report["scorecard_rows"][0]["closeout_status"] == "blocked"
    assert report["scorecard_rows"][-1]["completion_percent"] == 100.0
    assert report["unmet_criteria"][0]["criterion"] == "roi"


def test_domain_forwarding_renderers_and_empty_state() -> None:
    store = _store([])
    report = build_pilot_exit_criteria_scorecard_export(store, domain="enterprise")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="enterprise")
    assert json.loads(render_pilot_exit_criteria_scorecard_json(report)) == report
    assert "No pilot scorecard records found" in render_pilot_exit_criteria_scorecard_markdown(report)
