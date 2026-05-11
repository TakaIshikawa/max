"""Tests for release readiness scorecard exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports.release_readiness_scorecard import (
    SCHEMA_VERSION,
    build_release_readiness_scorecard_export,
    render_release_readiness_scorecard_csv,
    render_release_readiness_scorecard_json,
    render_release_readiness_scorecard_markdown,
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


def test_release_readiness_scorecard_export_and_renderers() -> None:
    report = build_release_readiness_scorecard_export(_store([
        _unit("bu-1", "Launch Console", {"qa_status": "complete", "docs_status": "complete", "security_review_status": "approved", "rollout_status": "ready", "dependency_risk": "low", "launch_date": "2026-06-01"}),
        _unit("bu-2", "Risky Importer", {"qa_status": "blocked", "docs_status": "pending", "security_review_status": "failed", "rollout_status": "pending", "dependency_risk": "high", "open_blockers": ["QA failure"]}),
    ]), domain="platform")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["source"]["domain_filter"] == "platform"
    assert report["summary"]["idea_count"] == 2
    assert report["summary"]["blocker_count"] == 1
    assert report["status_rollups"]["qa_status"]["blocked"] == 1
    assert report["ideas"][0]["readiness_band"] == "ready"
    assert report["blockers"][0]["blocker"] == "QA failure"

    markdown = render_release_readiness_scorecard_markdown(report)
    rendered_json = render_release_readiness_scorecard_json(report)
    rows = list(csv.DictReader(io.StringIO(render_release_readiness_scorecard_csv(report))))
    assert "## Blockers" in markdown
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rows[0]["idea_id"] == "bu-1"
