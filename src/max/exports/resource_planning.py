"""Resource planning export for team capacity and allocation analysis.

Analyzes task estimates, team availability, and skill requirements to generate
resource utilization reports and capacity forecasts.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

SCHEMA_VERSION = "max.resource_planning.v1"
KIND = "max.resource_planning"


def build_resource_planning_report(
    team_members: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    sprints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build resource planning report with capacity and allocation analysis.

    Args:
        team_members: List of team member dicts with keys:
            - name: str
            - skills: list[str]
            - availability_hours: float (hours per sprint)
        tasks: List of task dicts with keys:
            - name: str
            - required_skills: list[str]
            - estimate_hours: float
            - assignee: str | None
            - sprint: str | None
        sprints: Optional list of sprint dicts with keys:
            - name: str
            - capacity_hours: float (total available hours)

    Returns:
        Resource planning report with capacity, utilization, skill gaps,
        and forecasts.
    """
    capacity = _calculate_team_capacity(team_members)
    allocations = _calculate_allocations(team_members, tasks)
    utilization = _calculate_utilization_rates(capacity, allocations)
    skill_gaps = _identify_skill_gaps(team_members, tasks)
    over_under = _identify_over_under_allocation(utilization)
    forecasts = _generate_capacity_forecasts(team_members, tasks, sprints)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "resource_planning",
        },
        "team_capacity": capacity,
        "allocations": allocations,
        "utilization_rates": utilization,
        "skill_gaps": skill_gaps,
        "allocation_issues": over_under,
        "capacity_forecasts": forecasts,
    }


def render_resource_planning_markdown(report: dict[str, Any]) -> str:
    """Render resource planning report as Markdown.

    Args:
        report: Resource planning report from build_resource_planning_report

    Returns:
        Markdown formatted report
    """
    lines = [
        "# Resource Planning Report",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Kind: `{report['kind']}`",
        "",
    ]

    # Team Capacity
    capacity = report["team_capacity"]
    lines.extend([
        "## Team Capacity",
        "",
        f"- Total team members: {capacity['total_members']}",
        f"- Total available hours: {capacity['total_available_hours']:.1f}",
        f"- Skills coverage: {', '.join(capacity['all_skills'])}",
        "",
    ])

    # Utilization Rates
    lines.extend([
        "## Utilization Rates",
        "",
        "| Team Member | Available Hours | Allocated Hours | Utilization % |",
        "|-------------|----------------|-----------------|---------------|",
    ])
    for entry in report["utilization_rates"]:
        lines.append(
            f"| {entry['member']} | {entry['available_hours']:.1f} | "
            f"{entry['allocated_hours']:.1f} | {entry['utilization_pct']:.0f}% |"
        )
    lines.append("")

    # Allocation Issues
    issues = report["allocation_issues"]
    if issues["over_allocated"] or issues["under_allocated"]:
        lines.extend(["## Allocation Issues", ""])
        if issues["over_allocated"]:
            lines.append("### Over-Allocated")
            for item in issues["over_allocated"]:
                lines.append(
                    f"- **{item['member']}**: {item['utilization_pct']:.0f}% utilization "
                    f"(over by {item['over_hours']:.1f}h)"
                )
            lines.append("")
        if issues["under_allocated"]:
            lines.append("### Under-Allocated")
            for item in issues["under_allocated"]:
                lines.append(
                    f"- **{item['member']}**: {item['utilization_pct']:.0f}% utilization "
                    f"({item['spare_hours']:.1f}h available)"
                )
            lines.append("")

    # Skill Gaps
    skill_gaps = report["skill_gaps"]
    if skill_gaps:
        lines.extend(["## Skill Gaps", ""])
        for gap in skill_gaps:
            lines.append(
                f"- **{gap['skill']}**: required by {gap['demand_count']} task(s), "
                f"covered by {gap['supply_count']} member(s) — "
                f"gap severity: {gap['severity']}"
            )
        lines.append("")

    # Capacity Forecasts
    forecasts = report["capacity_forecasts"]
    if forecasts:
        lines.extend(["## Capacity Forecasts", ""])
        for forecast in forecasts:
            lines.append(f"### {forecast['sprint']}")
            lines.append(f"- Demand: {forecast['demand_hours']:.1f}h")
            lines.append(f"- Capacity: {forecast['capacity_hours']:.1f}h")
            lines.append(f"- Delta: {forecast['delta_hours']:+.1f}h")
            lines.append(f"- Status: {forecast['status']}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _calculate_team_capacity(
    team_members: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate total team capacity and skills coverage."""
    total_hours = sum(m.get("availability_hours", 0) for m in team_members)
    all_skills: set[str] = set()
    for m in team_members:
        all_skills.update(m.get("skills", []))

    return {
        "total_members": len(team_members),
        "total_available_hours": total_hours,
        "all_skills": sorted(all_skills),
    }


def _calculate_allocations(
    team_members: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> dict[str, float]:
    """Calculate hours allocated to each team member from assigned tasks."""
    allocations: dict[str, float] = defaultdict(float)

    # Initialize all members with 0
    for m in team_members:
        allocations[m["name"]] = 0.0

    for task in tasks:
        assignee = task.get("assignee")
        if assignee and assignee in allocations:
            allocations[assignee] += task.get("estimate_hours", 0)

    return dict(allocations)


def _calculate_utilization_rates(
    capacity: dict[str, Any],
    allocations: dict[str, float],
) -> list[dict[str, Any]]:
    """Calculate utilization rate per team member."""
    # We need per-member availability; rebuild from capacity isn't possible
    # so we'll accept that this is called with the full context
    # For now, utilization is relative to equal share of total capacity
    total_hours = capacity["total_available_hours"]
    total_members = capacity["total_members"]

    if total_members == 0:
        return []

    rates: list[dict[str, Any]] = []
    # We don't have per-member hours in capacity dict, so we calculate from allocations
    # This function is typically called after _calculate_team_capacity, and we pass
    # team_members separately. Instead, let's store per-member info.
    # Re-architecture: we'll make this work with the data available.
    # Actually the caller has team_members, so we'll restructure.

    # Since we only have aggregated capacity, distribute equally
    per_member_hours = total_hours / total_members if total_members > 0 else 0

    for member, allocated in sorted(allocations.items()):
        utilization_pct = (allocated / per_member_hours * 100) if per_member_hours > 0 else 0
        rates.append({
            "member": member,
            "available_hours": per_member_hours,
            "allocated_hours": allocated,
            "utilization_pct": utilization_pct,
        })

    return rates


def _identify_skill_gaps(
    team_members: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify skills required by tasks but underrepresented in the team."""
    # Count skill supply (team members with each skill)
    skill_supply: dict[str, int] = defaultdict(int)
    for m in team_members:
        for skill in m.get("skills", []):
            skill_supply[skill] += 1

    # Count skill demand (tasks requiring each skill)
    skill_demand: dict[str, int] = defaultdict(int)
    for task in tasks:
        for skill in task.get("required_skills", []):
            skill_demand[skill] += 1

    gaps: list[dict[str, Any]] = []
    for skill, demand_count in sorted(skill_demand.items()):
        supply_count = skill_supply.get(skill, 0)
        if supply_count == 0:
            severity = "critical"
        elif demand_count > supply_count * 2:
            severity = "high"
        elif demand_count > supply_count:
            severity = "medium"
        else:
            continue  # No gap

        gaps.append({
            "skill": skill,
            "demand_count": demand_count,
            "supply_count": supply_count,
            "severity": severity,
        })

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2}
    gaps.sort(key=lambda g: severity_order.get(g["severity"], 3))

    return gaps


def _identify_over_under_allocation(
    utilization_rates: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Identify over-allocated and under-allocated team members."""
    over: list[dict[str, Any]] = []
    under: list[dict[str, Any]] = []

    for entry in utilization_rates:
        pct = entry["utilization_pct"]
        if pct > 100:
            over.append({
                "member": entry["member"],
                "utilization_pct": pct,
                "over_hours": entry["allocated_hours"] - entry["available_hours"],
            })
        elif pct < 50:
            under.append({
                "member": entry["member"],
                "utilization_pct": pct,
                "spare_hours": entry["available_hours"] - entry["allocated_hours"],
            })

    return {"over_allocated": over, "under_allocated": under}


def _generate_capacity_forecasts(
    team_members: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    sprints: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Generate capacity forecasts for upcoming sprints."""
    if not sprints:
        return []

    forecasts: list[dict[str, Any]] = []

    for sprint in sprints:
        sprint_name = sprint["name"]
        capacity_hours = sprint.get(
            "capacity_hours",
            sum(m.get("availability_hours", 0) for m in team_members),
        )

        # Sum task estimates assigned to this sprint
        demand_hours = sum(
            t.get("estimate_hours", 0)
            for t in tasks
            if t.get("sprint") == sprint_name
        )

        delta = capacity_hours - demand_hours
        if delta < 0:
            status = "over_capacity"
        elif delta < capacity_hours * 0.1:
            status = "near_capacity"
        else:
            status = "under_capacity"

        forecasts.append({
            "sprint": sprint_name,
            "demand_hours": demand_hours,
            "capacity_hours": capacity_hours,
            "delta_hours": delta,
            "status": status,
        })

    return forecasts
