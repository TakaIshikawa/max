"""Tests for stakeholder mapping export."""

from __future__ import annotations

import json

from max.exports.stakeholder_map import (
    KIND,
    SCHEMA_VERSION,
    build_stakeholder_map,
    classify_quadrant,
    render_stakeholder_json,
    render_stakeholder_markdown,
)

# ── Test Data ────────────────────────────────────────────────────────

SAMPLE_STAKEHOLDERS = [
    {
        "name": "Alice Chen",
        "role": "VP Engineering",
        "influence": 0.9,
        "interest": 0.8,
        "notes": "Key decision maker for technical direction",
    },
    {
        "name": "Bob Martinez",
        "role": "CFO",
        "influence": 0.85,
        "interest": 0.3,
        "notes": "Concerned with budget only",
    },
    {
        "name": "Carol Davis",
        "role": "Developer",
        "influence": 0.2,
        "interest": 0.9,
        "notes": "Enthusiastic early adopter",
    },
    {
        "name": "Dan Wilson",
        "role": "External Auditor",
        "influence": 0.1,
        "interest": 0.2,
    },
]


# ── classify_quadrant tests ─────────────────────────────────────────


def test_classify_manage_closely() -> None:
    assert classify_quadrant(0.8, 0.7) == "manage_closely"


def test_classify_keep_satisfied() -> None:
    assert classify_quadrant(0.8, 0.3) == "keep_satisfied"


def test_classify_keep_informed() -> None:
    assert classify_quadrant(0.3, 0.7) == "keep_informed"


def test_classify_monitor() -> None:
    assert classify_quadrant(0.2, 0.2) == "monitor"


def test_classify_boundary_high() -> None:
    assert classify_quadrant(0.5, 0.5) == "manage_closely"


def test_classify_boundary_low() -> None:
    assert classify_quadrant(0.49, 0.49) == "monitor"


# ── build_stakeholder_map tests ─────────────────────────────────────


def test_build_schema() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["kind"] == KIND
    assert "generated_at" in doc


def test_build_project_name() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS, project_name="TestProject")
    assert doc["project_name"] == "TestProject"


def test_build_stakeholder_count() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    assert len(doc["stakeholders"]) == 4


def test_build_quadrant_assignment() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    stakeholders = {s["name"]: s for s in doc["stakeholders"]}
    assert stakeholders["Alice Chen"]["quadrant"] == "manage_closely"
    assert stakeholders["Bob Martinez"]["quadrant"] == "keep_satisfied"
    assert stakeholders["Carol Davis"]["quadrant"] == "keep_informed"
    assert stakeholders["Dan Wilson"]["quadrant"] == "monitor"


def test_build_engagement_strategies_assigned() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    for s in doc["stakeholders"]:
        assert s["engagement_strategy"] != ""


def test_build_quadrant_groups() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    groups = doc["quadrant_groups"]
    assert len(groups["manage_closely"]) == 1
    assert len(groups["keep_satisfied"]) == 1
    assert len(groups["keep_informed"]) == 1
    assert len(groups["monitor"]) == 1


def test_build_summary_counts() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    summary = doc["summary"]
    assert summary["manage_closely"] == 1
    assert summary["keep_satisfied"] == 1
    assert summary["keep_informed"] == 1
    assert summary["monitor"] == 1


def test_build_clamps_scores() -> None:
    stakeholders = [{"name": "X", "influence": 1.5, "interest": -0.3}]
    doc = build_stakeholder_map(stakeholders)
    s = doc["stakeholders"][0]
    assert s["influence"] == 1.0
    assert s["interest"] == 0.0


def test_build_empty() -> None:
    doc = build_stakeholder_map([])
    assert doc["stakeholders"] == []
    assert sum(doc["summary"].values()) == 0


# ── Markdown rendering ──────────────────────────────────────────────


def test_render_markdown_title() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS, project_name="TestApp")
    md = render_stakeholder_markdown(doc)
    assert "# Stakeholder Map — TestApp" in md


def test_render_markdown_summary() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    md = render_stakeholder_markdown(doc)
    assert "Total stakeholders: 4" in md


def test_render_markdown_quadrant_sections() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    md = render_stakeholder_markdown(doc)
    assert "## Manage Closely" in md
    assert "## Keep Satisfied" in md
    assert "## Keep Informed" in md
    assert "## Monitor" in md


def test_render_markdown_stakeholder_details() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    md = render_stakeholder_markdown(doc)
    assert "Alice Chen" in md
    assert "VP Engineering" in md
    assert "Influence: 90%" in md
    assert "Interest: 80%" in md


def test_render_markdown_notes() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    md = render_stakeholder_markdown(doc)
    assert "Key decision maker" in md


def test_render_markdown_strategy() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    md = render_stakeholder_markdown(doc)
    assert "Active engagement" in md


# ── JSON rendering ──────────────────────────────────────────────────


def test_render_json_valid() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS)
    output = render_stakeholder_json(doc)
    parsed = json.loads(output)
    assert parsed["schema_version"] == SCHEMA_VERSION


def test_render_json_roundtrip() -> None:
    doc = build_stakeholder_map(SAMPLE_STAKEHOLDERS, project_name="App")
    output = render_stakeholder_json(doc)
    parsed = json.loads(output)
    assert parsed["project_name"] == "App"
    assert len(parsed["stakeholders"]) == 4
