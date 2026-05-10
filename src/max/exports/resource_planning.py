"""Resource planning export with capacity analysis.

Generates team capacity and allocation reports. Analyzes task estimates,
team availability, and skill requirements. Exports resource utilization
and capacity forecasts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.resource_planning.v1"
KIND = "max.resource_planning"


def compute_utilization(allocated_hours: float, available_hours: float) -> float:
    """Compute utilization rate as a fraction 0.0–1.0.

    Args:
        allocated_hours: Hours allocated to tasks.
        available_hours: Total hours available.

    Returns:
        Utilization rate clamped to 0.0–1.0.
    """
    if available_hours <= 0:
        return 0.0
    return max(0.0, min(1.0, allocated_hours / available_hours))


def allocation_status(utilization: float) -> str:
    """Classify allocation status from utilization rate.

    Args:
        utilization: Utilization rate 0.0–1.0.

    Returns:
        One of "under_allocated", "balanced", "over_allocated".
    """
    if utilization < 0.5:
        return "under_allocated"
    if utilization > 0.85:
        return "over_allocated"
    return "balanced"


def _validate_member(member: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a team member entry."""
    available = max(0.0, float(member.get("available_hours", 40.0)))
    allocated = max(0.0, float(member.get("allocated_hours", 0.0)))
    skills = list(member.get("skills", []))
    utilization = compute_utilization(allocated, available)

    return {
        "name": member.get("name", "Unknown"),
        "role": member.get("role", ""),
        "available_hours": available,
        "allocated_hours": allocated,
        "utilization": round(utilization, 2),
        "status": allocation_status(utilization),
        "skills": skills,
    }


def _compute_skill_gaps(
    members: list[dict[str, Any]],
    required_skills: list[str],
) -> list[str]:
    """Identify skills required but not covered by any team member."""
    team_skills: set[str] = set()
    for m in members:
        team_skills.update(m.get("skills", []))
    return sorted(set(required_skills) - team_skills)


def _forecast_capacity(
    members: list[dict[str, Any]],
    sprints: int,
) -> list[dict[str, Any]]:
    """Generate capacity forecasts for upcoming sprints."""
    forecasts = []
    for sprint_num in range(1, sprints + 1):
        total_available = sum(m["available_hours"] for m in members)
        total_allocated = sum(m["allocated_hours"] for m in members)
        remaining = total_available - total_allocated
        forecasts.append({
            "sprint": sprint_num,
            "total_available_hours": total_available,
            "total_allocated_hours": total_allocated,
            "remaining_capacity_hours": max(0.0, remaining),
            "utilization": round(
                compute_utilization(total_allocated, total_available), 2
            ),
        })
    return forecasts


def build_resource_plan(
    members: list[dict[str, Any]],
    *,
    project_name: str = "Project",
    required_skills: list[str] | None = None,
    forecast_sprints: int = 3,
) -> dict[str, Any]:
    """Build a resource planning document.

    Args:
        members: List of team member dicts, each containing:
            - name: str
            - role: str (optional)
            - available_hours: float
            - allocated_hours: float
            - skills: list[str] (optional)
        project_name: Name of the project.
        required_skills: Skills needed for the project.
        forecast_sprints: Number of sprints to forecast.

    Returns:
        Structured resource planning document dict.
    """
    validated = [_validate_member(m) for m in members]
    skill_gaps = _compute_skill_gaps(validated, required_skills or [])
    forecasts = _forecast_capacity(validated, forecast_sprints)

    total_available = sum(m["available_hours"] for m in validated)
    total_allocated = sum(m["allocated_hours"] for m in validated)
    team_utilization = compute_utilization(total_allocated, total_available)

    over = [m for m in validated if m["status"] == "over_allocated"]
    under = [m for m in validated if m["status"] == "under_allocated"]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "members": validated,
        "skill_gaps": skill_gaps,
        "capacity_forecast": forecasts,
        "summary": {
            "total_members": len(validated),
            "total_available_hours": total_available,
            "total_allocated_hours": total_allocated,
            "team_utilization": round(team_utilization, 2),
            "over_allocated_count": len(over),
            "under_allocated_count": len(under),
        },
    }


def render_resource_markdown(document: dict[str, Any]) -> str:
    """Render resource plan as markdown.

    Args:
        document: Resource plan document from build_resource_plan.

    Returns:
        Markdown formatted resource report.
    """
    lines = [
        f"# Resource Plan — {document['project_name']}",
        "",
        "## Summary",
        "",
    ]

    summary = document["summary"]
    util_pct = int(summary["team_utilization"] * 100)
    lines.append(f"- **Team members**: {summary['total_members']}")
    lines.append(f"- **Total available hours**: {summary['total_available_hours']}")
    lines.append(f"- **Total allocated hours**: {summary['total_allocated_hours']}")
    lines.append(f"- **Team utilization**: {util_pct}%")
    lines.append(f"- **Over-allocated**: {summary['over_allocated_count']}")
    lines.append(f"- **Under-allocated**: {summary['under_allocated_count']}")
    lines.append("")

    # Skill gaps
    gaps = document.get("skill_gaps", [])
    if gaps:
        lines.append("## Skill Gaps")
        lines.append("")
        for skill in gaps:
            lines.append(f"- {skill}")
        lines.append("")

    # Team members
    lines.append("## Team Members")
    lines.append("")
    for m in document["members"]:
        util_pct_m = int(m["utilization"] * 100)
        role_str = f" ({m['role']})" if m["role"] else ""
        lines.append(f"### {m['name']}{role_str}")
        lines.append("")
        lines.append(f"- Available: {m['available_hours']}h")
        lines.append(f"- Allocated: {m['allocated_hours']}h")
        lines.append(f"- Utilization: {util_pct_m}%")
        lines.append(f"- Status: {m['status']}")
        if m["skills"]:
            lines.append(f"- Skills: {', '.join(m['skills'])}")
        lines.append("")

    # Capacity forecast
    forecasts = document.get("capacity_forecast", [])
    if forecasts:
        lines.append("## Capacity Forecast")
        lines.append("")
        for f in forecasts:
            util_f = int(f["utilization"] * 100)
            lines.append(f"### Sprint {f['sprint']}")
            lines.append("")
            lines.append(f"- Available: {f['total_available_hours']}h")
            lines.append(f"- Allocated: {f['total_allocated_hours']}h")
            lines.append(f"- Remaining: {f['remaining_capacity_hours']}h")
            lines.append(f"- Utilization: {util_f}%")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_resource_json(document: dict[str, Any]) -> str:
    """Render resource plan as formatted JSON."""
    return json.dumps(document, indent=2, default=str)
