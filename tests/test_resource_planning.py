"""Tests for resource planning export with capacity analysis."""

from __future__ import annotations

import json

from max.exports.resource_planning import (
    KIND,
    SCHEMA_VERSION,
    allocation_status,
    build_resource_plan,
    compute_utilization,
    render_resource_json,
    render_resource_markdown,
)

# ── Test Data ────────────────────────────────────────────────────────

SAMPLE_MEMBERS = [
    {
        "name": "Alice",
        "role": "Senior Engineer",
        "available_hours": 40.0,
        "allocated_hours": 35.0,
        "skills": ["python", "react", "aws"],
    },
    {
        "name": "Bob",
        "role": "Junior Engineer",
        "available_hours": 40.0,
        "allocated_hours": 15.0,
        "skills": ["python", "javascript"],
    },
    {
        "name": "Carol",
        "role": "Tech Lead",
        "available_hours": 32.0,
        "allocated_hours": 30.0,
        "skills": ["python", "architecture", "kubernetes"],
    },
]


# ── compute_utilization tests ───────────────────────────────────────


def test_utilization_normal() -> None:
    assert compute_utilization(30, 40) == 0.75


def test_utilization_full() -> None:
    assert compute_utilization(40, 40) == 1.0


def test_utilization_zero_available() -> None:
    assert compute_utilization(10, 0) == 0.0


def test_utilization_over() -> None:
    assert compute_utilization(50, 40) == 1.0


def test_utilization_none() -> None:
    assert compute_utilization(0, 40) == 0.0


# ── allocation_status tests ─────────────────────────────────────────


def test_status_balanced() -> None:
    assert allocation_status(0.7) == "balanced"


def test_status_over() -> None:
    assert allocation_status(0.9) == "over_allocated"


def test_status_under() -> None:
    assert allocation_status(0.3) == "under_allocated"


def test_status_boundary_balanced() -> None:
    assert allocation_status(0.5) == "balanced"


def test_status_boundary_over() -> None:
    assert allocation_status(0.85) == "balanced"


def test_status_boundary_over_above() -> None:
    assert allocation_status(0.86) == "over_allocated"


# ── build_resource_plan tests ───────────────────────────────────────


def test_build_schema() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS)
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["kind"] == KIND
    assert "generated_at" in doc


def test_build_project_name() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS, project_name="TestProject")
    assert doc["project_name"] == "TestProject"


def test_build_member_count() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS)
    assert len(doc["members"]) == 3


def test_build_utilization_calculated() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS)
    members = {m["name"]: m for m in doc["members"]}
    assert members["Alice"]["utilization"] == 0.88
    assert members["Bob"]["utilization"] == 0.38


def test_build_allocation_status() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS)
    members = {m["name"]: m for m in doc["members"]}
    assert members["Alice"]["status"] == "over_allocated"
    assert members["Bob"]["status"] == "under_allocated"
    assert members["Carol"]["status"] == "over_allocated"  # 30/32 = 0.9375


def test_build_skill_gaps() -> None:
    doc = build_resource_plan(
        SAMPLE_MEMBERS,
        required_skills=["python", "rust", "graphql"],
    )
    assert "rust" in doc["skill_gaps"]
    assert "graphql" in doc["skill_gaps"]
    assert "python" not in doc["skill_gaps"]


def test_build_no_skill_gaps() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS, required_skills=["python"])
    assert doc["skill_gaps"] == []


def test_build_capacity_forecast() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS, forecast_sprints=2)
    assert len(doc["capacity_forecast"]) == 2
    assert doc["capacity_forecast"][0]["sprint"] == 1
    assert doc["capacity_forecast"][1]["sprint"] == 2


def test_build_forecast_hours() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS, forecast_sprints=1)
    f = doc["capacity_forecast"][0]
    assert f["total_available_hours"] == 112.0
    assert f["total_allocated_hours"] == 80.0
    assert f["remaining_capacity_hours"] == 32.0


def test_build_summary() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS)
    summary = doc["summary"]
    assert summary["total_members"] == 3
    assert summary["total_available_hours"] == 112.0
    assert summary["total_allocated_hours"] == 80.0
    assert summary["over_allocated_count"] == 2  # Alice + Carol
    assert summary["under_allocated_count"] == 1


def test_build_empty() -> None:
    doc = build_resource_plan([])
    assert doc["members"] == []
    assert doc["summary"]["total_members"] == 0


# ── Markdown rendering ──────────────────────────────────────────────


def test_render_markdown_title() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS, project_name="TestApp")
    md = render_resource_markdown(doc)
    assert "# Resource Plan — TestApp" in md


def test_render_markdown_summary() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS)
    md = render_resource_markdown(doc)
    assert "Team members" in md
    assert "Team utilization" in md


def test_render_markdown_skill_gaps() -> None:
    doc = build_resource_plan(
        SAMPLE_MEMBERS, required_skills=["python", "rust"]
    )
    md = render_resource_markdown(doc)
    assert "## Skill Gaps" in md
    assert "rust" in md


def test_render_markdown_members() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS)
    md = render_resource_markdown(doc)
    assert "Alice" in md
    assert "Senior Engineer" in md
    assert "over_allocated" in md


def test_render_markdown_forecast() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS, forecast_sprints=2)
    md = render_resource_markdown(doc)
    assert "## Capacity Forecast" in md
    assert "Sprint 1" in md
    assert "Sprint 2" in md


# ── JSON rendering ──────────────────────────────────────────────────


def test_render_json_valid() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS)
    output = render_resource_json(doc)
    parsed = json.loads(output)
    assert parsed["schema_version"] == SCHEMA_VERSION


def test_render_json_roundtrip() -> None:
    doc = build_resource_plan(SAMPLE_MEMBERS, project_name="App")
    output = render_resource_json(doc)
    parsed = json.loads(output)
    assert parsed["project_name"] == "App"
    assert len(parsed["members"]) == 3
