"""Deterministic sprint planning exports for persisted design briefs."""

from __future__ import annotations

from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.sprint_planning.v1"
KIND = "max.design_brief.sprint_planning"


def build_design_brief_sprint_planning(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build a sprint planning document from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _sprint_planning_context(design_brief, source_ideas)
    sprint_goals = _sprint_goals(context, source_idea_ids)
    capacity_planning = _capacity_planning(context, source_idea_ids)
    story_estimates = _story_point_estimates(context, source_idea_ids)
    task_breakdown = _task_breakdown(context, story_estimates, source_idea_ids)
    velocity = _team_velocity(context, source_idea_ids)
    burndown = _burndown_projections(velocity, story_estimates, source_idea_ids)
    commitments = _sprint_commitments(sprint_goals, capacity_planning, source_idea_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "planning_goal": f"Define sprint planning for {design_brief['title']}.",
            "sprint_count": len(sprint_goals),
            "total_story_points": sum(s["story_points"] for s in story_estimates),
            "team_capacity": capacity_planning.get("total_capacity", 0),
            "estimated_velocity": velocity.get("estimated_velocity", 0),
        },
        "sprint_goals": sprint_goals,
        "capacity_planning": capacity_planning,
        "story_point_estimates": story_estimates,
        "task_breakdown": task_breakdown,
        "team_velocity": velocity,
        "burndown_projections": burndown,
        "sprint_commitments": commitments,
        "source_ideas": source_ideas,
    }


def render_design_brief_sprint_planning_markdown(plan: dict[str, Any]) -> str:
    """Render the sprint planning document as formatted markdown."""
    brief = plan["design_brief"]
    summary = plan["summary"]
    sprint_goals = plan["sprint_goals"]
    capacity = plan["capacity_planning"]
    estimates = plan["story_point_estimates"]
    tasks = plan["task_breakdown"]
    velocity = plan["team_velocity"]
    burndown = plan["burndown_projections"]
    commitments = plan["sprint_commitments"]

    lines = [
        f"# {brief['title']} Sprint Planning",
        "",
        f"**Brief ID**: {brief['id']}",
        f"**Domain**: {brief['domain']}",
        f"**Theme**: {brief['theme']}",
        f"**Design Status**: {brief['design_status']}",
        f"**Readiness Score**: {brief['readiness_score']}",
        "",
        "## Summary",
        "",
        f"- **Planning Goal**: {summary['planning_goal']}",
        f"- **Sprint Count**: {summary['sprint_count']}",
        f"- **Total Story Points**: {summary['total_story_points']}",
        f"- **Team Capacity**: {summary['team_capacity']}",
        f"- **Estimated Velocity**: {summary['estimated_velocity']}",
        "",
        "## Sprint Goals",
        "",
    ]

    if sprint_goals:
        for goal in sprint_goals:
            lines.extend([
                f"### {goal['sprint_id']}: {goal['goal']}",
                "",
                f"- **Duration**: {goal['duration']}",
                f"- **Team**: {goal['team']}",
                f"- **Success Criteria**: {goal['success_criteria']}",
                "",
            ])
    else:
        lines.append("No sprint goals defined.")
        lines.append("")

    lines.extend([
        "## Capacity Planning",
        "",
        f"- **Total Capacity**: {capacity.get('total_capacity', 0)} story points",
        f"- **Available Hours**: {capacity.get('available_hours', 0)} hours",
        f"- **Team Size**: {capacity.get('team_size', 0)} people",
        "",
    ])

    if capacity.get("capacity_allocation"):
        lines.append("### Capacity Allocation")
        lines.append("")
        lines.append("| Role | Hours | Story Points |")
        lines.append("|------|-------|--------------|")
        for alloc in capacity["capacity_allocation"]:
            lines.append(f"| {alloc['role']} | {alloc['hours']} | {alloc['story_points']} |")
        lines.append("")

    lines.extend([
        "## Story Point Estimates",
        "",
    ])

    if estimates:
        lines.append("| Story ID | Story Title | Story Points | Priority |")
        lines.append("|----------|-------------|--------------|----------|")
        for est in estimates:
            lines.append(f"| {est['story_id']} | {est['title']} | {est['story_points']} | {est['priority']} |")
        lines.append("")
    else:
        lines.append("No story estimates available.")
        lines.append("")

    lines.extend([
        "## Task Breakdown",
        "",
    ])

    if tasks.get("task_matrix"):
        lines.append("### Task Matrix")
        lines.append("")
        lines.append("| Task ID | Story ID | Task | Owner | Est. Hours |")
        lines.append("|---------|----------|------|-------|------------|")
        for task in tasks["task_matrix"]:
            lines.append(f"| {task['task_id']} | {task['story_id']} | {task['task']} | {task['owner']} | {task['estimated_hours']} |")
        lines.append("")
    else:
        lines.append("No task breakdown available.")
        lines.append("")

    lines.extend([
        "## Team Velocity",
        "",
        f"- **Historical Velocity**: {velocity.get('historical_velocity', 'N/A')}",
        f"- **Estimated Velocity**: {velocity.get('estimated_velocity', 0)} story points/sprint",
        f"- **Velocity Trend**: {velocity.get('velocity_trend', 'stable')}",
        "",
        "## Burndown Projections",
        "",
    ])

    if burndown.get("projections"):
        lines.append("| Sprint | Remaining Points | Projected Completion |")
        lines.append("|--------|------------------|----------------------|")
        for proj in burndown["projections"]:
            lines.append(f"| {proj['sprint']} | {proj['remaining_points']} | {proj['projected_completion']} |")
        lines.append("")
    else:
        lines.append("No burndown projections available.")
        lines.append("")

    lines.extend([
        "## Sprint Commitments",
        "",
    ])

    if commitments:
        for commit in commitments:
            lines.extend([
                f"### {commit['sprint_id']}",
                "",
                f"- **Committed Stories**: {len(commit.get('committed_stories', []))}",
                f"- **Committed Points**: {commit.get('committed_points', 0)}",
                f"- **Capacity Used**: {commit.get('capacity_used_percent', 0)}%",
                "",
            ])
    else:
        lines.append("No sprint commitments defined.")
        lines.append("")

    return "\n".join(lines)


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    """Load source buildable ideas from the design brief."""
    idea_ids = design_brief.get("source_idea_ids") or []
    ideas: list[dict[str, Any]] = []
    for idea_id in idea_ids:
        unit = store.get_buildable_unit(idea_id)
        if unit:
            ideas.append({
                "id": unit.id,
                "title": unit.title,
                "category": str(unit.category),
                "domain": unit.domain,
            })
        else:
            ideas.append({"id": idea_id, "missing": True})
    return ideas


def _sprint_planning_context(
    design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build context for sprint planning from design brief and source ideas."""
    return {
        "title": design_brief["title"],
        "theme": design_brief.get("theme", ""),
        "domain": design_brief.get("domain", ""),
        "idea_count": len([i for i in source_ideas if not i.get("missing")]),
    }


def _sprint_goals(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, str]]:
    """Generate sprint goals based on context."""
    return [
        {
            "sprint_id": "sprint_1",
            "goal": f"Establish foundation for {context['title']}",
            "duration": "2 weeks",
            "team": "core_team",
            "success_criteria": "Core infrastructure deployed and tested",
        },
        {
            "sprint_id": "sprint_2",
            "goal": f"Build core features for {context['title']}",
            "duration": "2 weeks",
            "team": "core_team",
            "success_criteria": "Primary user workflows functional",
        },
    ]


def _capacity_planning(context: dict[str, Any], source_idea_ids: list[str]) -> dict[str, Any]:
    """Generate capacity planning data."""
    return {
        "total_capacity": 40,
        "available_hours": 320,
        "team_size": 4,
        "capacity_allocation": [
            {"role": "frontend_engineer", "hours": 80, "story_points": 10},
            {"role": "backend_engineer", "hours": 80, "story_points": 10},
            {"role": "designer", "hours": 80, "story_points": 10},
            {"role": "qa_engineer", "hours": 80, "story_points": 10},
        ],
    }


def _story_point_estimates(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    """Generate story point estimates."""
    return [
        {
            "story_id": "story_001",
            "title": f"Set up {context['title']} infrastructure",
            "story_points": 8,
            "priority": "high",
        },
        {
            "story_id": "story_002",
            "title": f"Implement core workflow for {context['title']}",
            "story_points": 13,
            "priority": "high",
        },
    ]


def _task_breakdown(
    context: dict[str, Any], estimates: list[dict[str, Any]], source_idea_ids: list[str]
) -> dict[str, Any]:
    """Generate task breakdown from story estimates."""
    return {
        "task_matrix": [
            {
                "task_id": "task_001",
                "story_id": "story_001",
                "task": "Set up development environment",
                "owner": "backend_engineer",
                "estimated_hours": 16,
            },
            {
                "task_id": "task_002",
                "story_id": "story_001",
                "task": "Configure CI/CD pipeline",
                "owner": "backend_engineer",
                "estimated_hours": 24,
            },
        ],
    }


def _team_velocity(context: dict[str, Any], source_idea_ids: list[str]) -> dict[str, Any]:
    """Calculate team velocity metrics."""
    return {
        "historical_velocity": "N/A",
        "estimated_velocity": 20,
        "velocity_trend": "stable",
    }


def _burndown_projections(
    velocity: dict[str, Any], estimates: list[dict[str, Any]], source_idea_ids: list[str]
) -> dict[str, Any]:
    """Generate burndown chart projections."""
    total_points = sum(e["story_points"] for e in estimates)
    velocity_per_sprint = velocity.get("estimated_velocity", 20)

    projections = []
    remaining = total_points
    sprint_num = 1

    while remaining > 0:
        projections.append({
            "sprint": f"sprint_{sprint_num}",
            "remaining_points": remaining,
            "projected_completion": f"{100 - (remaining / total_points * 100):.0f}%" if total_points > 0 else "0%",
        })
        remaining -= velocity_per_sprint
        sprint_num += 1

        if sprint_num > 10:  # Safety limit
            break

    return {"projections": projections}


def _sprint_commitments(
    goals: list[dict[str, str]], capacity: dict[str, Any], source_idea_ids: list[str]
) -> list[dict[str, Any]]:
    """Generate sprint commitments based on goals and capacity."""
    return [
        {
            "sprint_id": goal["sprint_id"],
            "committed_stories": ["story_001"],
            "committed_points": 8,
            "capacity_used_percent": 20,
        }
        for goal in goals
    ]
