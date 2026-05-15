from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_expansion_readiness_scorecard_export
from max.exports.expansion_readiness_scorecard import (
    SCHEMA_VERSION,
    render_expansion_readiness_scorecard_json,
    render_expansion_readiness_scorecard_markdown,
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


def test_scores_ready_watch_and_blocked_accounts() -> None:
    report = build_expansion_readiness_scorecard_export(_store([
        _unit("ready", "Ready Co", {"usage": "high", "adoption": "healthy", "stakeholders": "strong", "integrations": "deep", "renewal": "ready", "support_load": "low"}),
        _unit("blocked", "Blocked Co", {"usage": "declining", "adoption": "weak", "support_load": "high escalation"}),
        _unit("watch", "Watch Co", {}),
    ]))

    assert [row["idea_id"] for row in report["accounts"]] == ["ready", "watch", "blocked"]
    assert report["accounts"][0]["score_band"] == "ready"
    assert report["accounts"][2]["expansion_blockers"]
    assert report["summary"]["band_counts"] == {"ready": 1, "watch": 1, "blocked": 1}


def test_missing_evidence_and_renderers_are_stable() -> None:
    report = build_expansion_readiness_scorecard_export(_store([]), domain="enterprise")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["summary"]["account_count"] == 0
    assert "No accounts available" in render_expansion_readiness_scorecard_markdown(report)
    assert json.loads(render_expansion_readiness_scorecard_json(report))["source"]["domain_filter"] == "enterprise"
