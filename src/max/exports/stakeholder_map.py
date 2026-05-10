"""Stakeholder mapping export with power/interest matrix.

Visualizes project stakeholders, their interests, and influence levels.
Generates a stakeholder matrix with engagement strategies per quadrant.
Exports to markdown and structured JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.stakeholder_map.v1"
KIND = "max.stakeholder_map"

QUADRANTS = {
    "manage_closely": "Manage Closely",
    "keep_satisfied": "Keep Satisfied",
    "keep_informed": "Keep Informed",
    "monitor": "Monitor",
}

ENGAGEMENT_STRATEGIES: dict[str, str] = {
    "manage_closely": "Active engagement: regular meetings, involve in key decisions, seek input on direction.",
    "keep_satisfied": "Keep satisfied: provide updates on impact areas, consult on major changes, respect their authority.",
    "keep_informed": "Keep informed: regular communications, address concerns promptly, leverage their enthusiasm.",
    "monitor": "Monitor: periodic updates, minimal effort, watch for changes in interest or influence.",
}


def classify_quadrant(influence: float, interest: float) -> str:
    """Classify a stakeholder into a power/interest quadrant.

    Args:
        influence: Influence score 0.0–1.0 (power axis).
        interest: Interest score 0.0–1.0.

    Returns:
        Quadrant key string.
    """
    high_influence = influence >= 0.5
    high_interest = interest >= 0.5

    if high_influence and high_interest:
        return "manage_closely"
    if high_influence and not high_interest:
        return "keep_satisfied"
    if not high_influence and high_interest:
        return "keep_informed"
    return "monitor"


def _validate_stakeholder(stakeholder: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a stakeholder entry."""
    influence = max(0.0, min(1.0, float(stakeholder.get("influence", 0.5))))
    interest = max(0.0, min(1.0, float(stakeholder.get("interest", 0.5))))
    quadrant = classify_quadrant(influence, interest)
    return {
        "name": stakeholder.get("name", "Unknown"),
        "role": stakeholder.get("role", ""),
        "influence": influence,
        "interest": interest,
        "quadrant": quadrant,
        "engagement_strategy": ENGAGEMENT_STRATEGIES[quadrant],
        "notes": stakeholder.get("notes", ""),
    }


def build_stakeholder_map(
    stakeholders: list[dict[str, Any]],
    *,
    project_name: str = "Project",
) -> dict[str, Any]:
    """Build a stakeholder map document.

    Args:
        stakeholders: List of stakeholder dicts, each containing:
            - name: str
            - role: str (optional)
            - influence: float 0.0–1.0
            - interest: float 0.0–1.0
            - notes: str (optional)
        project_name: Name of the project.

    Returns:
        Structured stakeholder map document dict.
    """
    validated = [_validate_stakeholder(s) for s in stakeholders]

    quadrant_groups: dict[str, list[dict[str, Any]]] = {q: [] for q in QUADRANTS}
    for s in validated:
        quadrant_groups[s["quadrant"]].append(s)

    summary = {q: len(members) for q, members in quadrant_groups.items()}

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "stakeholders": validated,
        "quadrant_groups": quadrant_groups,
        "summary": summary,
    }


def render_stakeholder_markdown(document: dict[str, Any]) -> str:
    """Render stakeholder map as markdown.

    Args:
        document: Stakeholder map document from build_stakeholder_map.

    Returns:
        Markdown formatted stakeholder map.
    """
    lines = [
        f"# Stakeholder Map — {document['project_name']}",
        "",
        "## Summary",
        "",
    ]

    summary = document["summary"]
    total = sum(summary.values())
    lines.append(f"Total stakeholders: {total}")
    lines.append("")
    for qkey, label in QUADRANTS.items():
        count = summary.get(qkey, 0)
        lines.append(f"- **{label}**: {count}")
    lines.append("")

    # Render each quadrant
    quadrant_groups = document["quadrant_groups"]
    for qkey, label in QUADRANTS.items():
        members = quadrant_groups.get(qkey, [])
        lines.append(f"## {label}")
        lines.append("")
        lines.append(f"*Strategy: {ENGAGEMENT_STRATEGIES[qkey]}*")
        lines.append("")
        if not members:
            lines.append("No stakeholders in this quadrant.")
            lines.append("")
            continue
        for s in members:
            influence_pct = int(s["influence"] * 100)
            interest_pct = int(s["interest"] * 100)
            role_str = f" ({s['role']})" if s["role"] else ""
            lines.append(f"### {s['name']}{role_str}")
            lines.append("")
            lines.append(f"- Influence: {influence_pct}%")
            lines.append(f"- Interest: {interest_pct}%")
            if s["notes"]:
                lines.append(f"- Notes: {s['notes']}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_stakeholder_json(document: dict[str, Any]) -> str:
    """Render stakeholder map as formatted JSON.

    Args:
        document: Stakeholder map document from build_stakeholder_map.

    Returns:
        JSON formatted string.
    """
    return json.dumps(document, indent=2, default=str)
