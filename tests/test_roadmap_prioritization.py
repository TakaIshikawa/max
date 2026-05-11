"""Tests for roadmap prioritization exports."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

from max.exports.roadmap_prioritization import (
    SCHEMA_VERSION,
    build_roadmap_prioritization_export,
    render_roadmap_prioritization_csv,
    render_roadmap_prioritization_json,
    render_roadmap_prioritization_markdown,
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


def test_roadmap_prioritization_ranks_and_renders() -> None:
    report = build_roadmap_prioritization_export(_store([
        _unit("bu-2", "Minor Polish", {"impact_score": 2, "effort_score": 3, "confidence_score": 0.5, "strategic_alignment": 1, "target_quarter": "2026Q3"}),
        _unit("bu-1", "Revenue Workflow", {"impact_score": 9, "effort_score": 1, "confidence_score": 0.9, "strategic_alignment": 5, "customer_requests": 30, "revenue_potential": 250000, "target_quarter": "2026Q2"}),
    ]))

    assert report["schema_version"] == SCHEMA_VERSION
    assert [row["idea_id"] for row in report["ranked_items"]] == ["bu-1", "bu-2"]
    assert report["ranked_items"][0]["rank"] == 1
    assert report["ranked_items"][0]["priority_band"] == "high"
    assert report["quarter_rollups"][0]["target_quarter"] == "2026Q2"

    markdown = render_roadmap_prioritization_markdown(report)
    rendered_json = render_roadmap_prioritization_json(report)
    rows = list(csv.DictReader(io.StringIO(render_roadmap_prioritization_csv(report))))
    assert "## Top Priorities" in markdown
    assert "## Quarter Summary" in markdown
    assert json.loads(rendered_json)["schema_version"] == SCHEMA_VERSION
    assert rows[0]["rank"] == "1"
