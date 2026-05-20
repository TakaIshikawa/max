from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.stakeholder_engagement_gaps import (
    build_stakeholder_engagement_gaps_export,
    render_stakeholder_engagement_gaps_json,
    render_stakeholder_engagement_gaps_markdown,
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


def test_engagement_gaps_classify_and_sort() -> None:
    report = build_stakeholder_engagement_gaps_export(
        _store(
            [
                _unit("low", {"account": "Zenith", "required_roles": ["economic buyer"], "engaged_roles": ["economic buyer"], "last_touch_days": 5, "champion_status": "strong", "executive_sponsor": "Ari", "decision_owner": "Lee"}),
                _unit("medium", {"account": "Beta", "required_roles": ["security"], "engaged_roles": [], "last_touch_days": 10, "champion_status": "strong", "executive_sponsor": "Ari", "decision_owner": "Lee"}),
                _unit("high", {"account": "Acme", "required_roles": ["security", "legal"], "engaged_roles": ["legal"], "last_touch_days": 45, "champion_status": "missing", "blockers": ["no meeting"]}),
            ]
        )
    )

    assert [row["idea_id"] for row in report["engagement_rows"]] == ["high", "medium", "low"]
    assert report["engagement_rows"][0]["engagement_risk"] == "high"
    assert report["engagement_rows"][0]["missing_required_roles"] == ["security"]
    assert report["missing_roles"][0] == {"role": "security", "count": 2}


def test_domain_forwarding_renderers_and_empty_state() -> None:
    store = _store([])
    report = build_stakeholder_engagement_gaps_export(store, domain="sales")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="sales")
    assert json.loads(render_stakeholder_engagement_gaps_json(report)) == report
    assert "No stakeholder engagement records found" in render_stakeholder_engagement_gaps_markdown(report)
