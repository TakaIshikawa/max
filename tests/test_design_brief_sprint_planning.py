"""Tests for design brief sprint planning generation and markdown rendering."""

from __future__ import annotations

import pytest

from max.analysis.design_brief_sprint_planning import (
    build_design_brief_sprint_planning,
    render_design_brief_sprint_planning_markdown,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def sample_design_brief_with_sprint_data(store):
    """Create a sample design brief with sprint planning data."""
    unit1 = BuildableUnit(
        id="bu-sprint001",
        title="User Authentication Module",
        one_liner="Secure user authentication system",
        category=BuildableCategory.FEATURE,
        ideation_mode=IdeationMode.DIRECT,
        problem="No secure authentication",
        solution="OAuth2-based authentication",
        target_users="both",
        value_proposition="Secure and scalable authentication",
        specific_user="backend engineer",
        domain="security",
    )
    store.insert_buildable_unit(unit1)

    brief = ProjectBrief(
        title="Sprint Planning Test Brief",
        domain="engineering",
        theme="development",
        lead=Candidate(unit=unit1),
        supporting=[],
        readiness_score=85.0,
        why_this_now="Testing sprint planning functionality",
    )
    brief_id = store.insert_design_brief(brief)
    return brief_id


def test_build_design_brief_sprint_planning_creates_valid_structure(
    store, sample_design_brief_with_sprint_data
):
    plan = build_design_brief_sprint_planning(store, sample_design_brief_with_sprint_data)

    assert plan is not None
    assert plan["schema_version"] == "max.design_brief.sprint_planning.v1"
    assert plan["kind"] == "max.design_brief.sprint_planning"
    assert plan["design_brief"]["id"] == sample_design_brief_with_sprint_data
    assert plan["design_brief"]["title"] == "Sprint Planning Test Brief"


def test_build_design_brief_sprint_planning_includes_all_sections(
    store, sample_design_brief_with_sprint_data
):
    plan = build_design_brief_sprint_planning(store, sample_design_brief_with_sprint_data)

    assert "sprint_goals" in plan
    assert "capacity_planning" in plan
    assert "story_point_estimates" in plan
    assert "task_breakdown" in plan
    assert "team_velocity" in plan
    assert "burndown_projections" in plan
    assert "sprint_commitments" in plan
    assert "summary" in plan


def test_build_design_brief_sprint_planning_summary_completeness(
    store, sample_design_brief_with_sprint_data
):
    plan = build_design_brief_sprint_planning(store, sample_design_brief_with_sprint_data)

    summary = plan["summary"]
    assert "planning_goal" in summary
    assert "sprint_count" in summary
    assert "total_story_points" in summary
    assert "team_capacity" in summary
    assert "estimated_velocity" in summary
    assert summary["sprint_count"] > 0
    assert summary["total_story_points"] > 0


def test_render_design_brief_sprint_planning_markdown_structure(
    store, sample_design_brief_with_sprint_data
):
    plan = build_design_brief_sprint_planning(store, sample_design_brief_with_sprint_data)
    markdown = render_design_brief_sprint_planning_markdown(plan)

    assert "# Sprint Planning Test Brief Sprint Planning" in markdown
    assert "## Summary" in markdown
    assert "## Sprint Goals" in markdown
    assert "## Capacity Planning" in markdown
    assert "## Story Point Estimates" in markdown
    assert "## Task Breakdown" in markdown
    assert "## Team Velocity" in markdown
    assert "## Burndown Projections" in markdown
    assert "## Sprint Commitments" in markdown


def test_render_design_brief_sprint_planning_markdown_tables(
    store, sample_design_brief_with_sprint_data
):
    plan = build_design_brief_sprint_planning(store, sample_design_brief_with_sprint_data)
    markdown = render_design_brief_sprint_planning_markdown(plan)

    # Check for table headers
    assert "| Role | Hours | Story Points |" in markdown
    assert "| Story ID | Story Title | Story Points | Priority |" in markdown
    assert "| Task ID | Story ID | Task | Owner | Est. Hours |" in markdown
    assert "| Sprint | Remaining Points | Projected Completion |" in markdown

    # Check for table separators
    assert "|------|-------|--------------|" in markdown
    assert "|----------|-------------|--------------|----------|" in markdown


def test_render_design_brief_sprint_planning_markdown_completeness(
    store, sample_design_brief_with_sprint_data
):
    plan = build_design_brief_sprint_planning(store, sample_design_brief_with_sprint_data)
    markdown = render_design_brief_sprint_planning_markdown(plan)

    # Verify key data is present
    assert "Sprint Planning Test Brief" in markdown
    assert "sprint_1" in markdown
    assert "sprint_2" in markdown
    assert "story_001" in markdown
    assert "story_002" in markdown
    assert "frontend_engineer" in markdown
    assert "backend_engineer" in markdown
    assert "task_001" in markdown


def test_build_design_brief_sprint_planning_returns_none_for_missing_brief(store):
    plan = build_design_brief_sprint_planning(store, "nonexistent-brief-id")
    assert plan is None
