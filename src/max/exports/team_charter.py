"""Team charter document export.

Defines team mission, scope, roles, decision-making processes, and
communication norms. Exports structured markdown with RACI matrices
and escalation paths.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.team_charter.v1"
KIND = "max.team_charter"

# RACI roles
RESPONSIBLE = "R"
ACCOUNTABLE = "A"
CONSULTED = "C"
INFORMED = "I"


def build_team_charter(
    store: Store,
    domain: str | None = None,
    *,
    team_name: str = "Product & Engineering",
) -> dict[str, Any]:
    """Build team charter from signals and buildable units.

    Args:
        store: Database store containing signals and buildable units.
        domain: Optional domain filter.
        team_name: Name of the team for the charter.

    Returns:
        Dict with charter data including mission, scope, RACI, and communication norms.
    """
    units = store.get_buildable_units(limit=1000, domain=domain)
    signals = store.get_signals(limit=1000)

    mission = _derive_mission(units, signals, team_name)
    scope = _define_scope(units, signals)
    roles = _define_roles(units)
    raci_matrix = _build_raci_matrix(units)
    communication = _define_communication_norms(signals)
    escalation = _define_escalation_paths()
    decision_making = _define_decision_process()

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "team_charter",
            "domain_filter": domain,
        },
        "team_name": team_name,
        "mission": mission,
        "scope": scope,
        "roles": roles,
        "raci_matrix": raci_matrix,
        "communication": communication,
        "escalation_paths": escalation,
        "decision_making": decision_making,
    }


def render_team_charter_markdown(report: dict[str, Any]) -> str:
    """Render team charter as Markdown."""
    lines = [
        f"# Team Charter — {report['team_name']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
    ]

    # Mission
    lines.extend([
        "## Mission Statement",
        "",
        report["mission"],
        "",
    ])

    # Scope
    lines.extend(["## Scope", ""])
    scope = report["scope"]
    lines.extend(["### In Scope", ""])
    for item in scope.get("in_scope", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.extend(["### Out of Scope", ""])
    for item in scope.get("out_of_scope", []):
        lines.append(f"- {item}")
    lines.append("")

    # Roles
    lines.extend(["## Roles & Responsibilities", ""])
    for role in report["roles"]:
        lines.append(f"- **{role['title']}**: {role['responsibilities']}")
    lines.append("")

    # RACI Matrix
    lines.extend(["## RACI Matrix", ""])
    raci = report["raci_matrix"]
    if raci["activities"] and raci["roles"]:
        header = "| Activity | " + " | ".join(raci["roles"]) + " |"
        sep = "|----------|" + "|".join(["---"] * len(raci["roles"])) + "|"
        lines.extend([header, sep])
        for row in raci["activities"]:
            cells = " | ".join(row["assignments"])
            lines.append(f"| {row['activity']} | {cells} |")
        lines.append("")
    else:
        lines.extend(["- No RACI data available", ""])

    # Communication
    lines.extend(["## Communication Norms", ""])
    comm = report["communication"]
    lines.extend(["### Channels", ""])
    for ch in comm.get("channels", []):
        lines.append(f"- **{ch['name']}**: {ch['purpose']}")
    lines.append("")
    lines.extend(["### Meeting Cadences", ""])
    for mtg in comm.get("meetings", []):
        lines.append(f"- **{mtg['name']}**: {mtg['frequency']} — {mtg['purpose']}")
    lines.append("")

    # Escalation
    lines.extend(["## Escalation Paths", ""])
    for path in report["escalation_paths"]:
        lines.append(f"- **{path['level']}**: {path['action']}")
    lines.append("")

    # Decision Making
    lines.extend(["## Decision-Making Process", ""])
    dm = report["decision_making"]
    lines.append(f"**Model**: {dm['model']}")
    lines.append("")
    for step in dm.get("steps", []):
        lines.append(f"1. {step}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_team_charter_json(report: dict[str, Any]) -> str:
    """Render team charter as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _derive_mission(
    units: list[Any],
    signals: list[Any],
    team_name: str,
) -> str:
    """Derive team mission statement from data context."""
    domains = sorted({getattr(u, "domain", "") for u in units} - {""})
    source_types = sorted({str(s.source_type) for s in signals})

    parts = [f"The {team_name} team drives"]

    if domains:
        parts.append(f"innovation across {', '.join(domains[:3])}")
    else:
        parts.append("product and technology innovation")

    if source_types:
        parts.append(
            f"by leveraging insights from {len(source_types)} intelligence source(s)"
        )

    parts.append(
        "to deliver high-impact solutions that address market needs "
        "and create sustainable competitive advantage."
    )

    return " ".join(parts)


def _define_scope(
    units: list[Any],
    signals: list[Any],
) -> dict[str, list[str]]:
    """Define team scope from units and signals."""
    in_scope: list[str] = []
    out_of_scope: list[str] = []

    # In-scope from domains
    domains = sorted({getattr(u, "domain", "") for u in units} - {""})
    for domain in domains:
        in_scope.append(f"Product development in {domain}")

    # In-scope from activities
    if signals:
        in_scope.append("Market intelligence collection and analysis")
    if units:
        in_scope.append("Buildable unit identification and prioritization")

    in_scope.append("Technical architecture and implementation")
    in_scope.append("Quality assurance and testing")

    # Out of scope
    out_of_scope.extend([
        "Sales and customer acquisition",
        "Legal and regulatory compliance",
        "Financial planning and budgeting",
        "HR and talent management",
    ])

    return {"in_scope": in_scope, "out_of_scope": out_of_scope}


def _define_roles(units: list[Any]) -> list[dict[str, str]]:
    """Define team roles based on project needs."""
    roles = [
        {
            "title": "Product Lead",
            "responsibilities": "Owns product vision, roadmap prioritization, and stakeholder communication",
        },
        {
            "title": "Tech Lead",
            "responsibilities": "Drives technical architecture, code quality standards, and engineering practices",
        },
        {
            "title": "Signal Analyst",
            "responsibilities": "Collects, validates, and synthesizes market intelligence signals",
        },
    ]

    domains = sorted({getattr(u, "domain", "") for u in units} - {""})
    if domains:
        roles.append({
            "title": "Domain Specialist",
            "responsibilities": f"Subject matter expertise in {', '.join(domains[:3])}",
        })

    return roles


def _build_raci_matrix(units: list[Any]) -> dict[str, Any]:
    """Build RACI matrix for key activities."""
    roles = ["Product Lead", "Tech Lead", "Signal Analyst"]

    domains = sorted({getattr(u, "domain", "") for u in units} - {""})
    if domains:
        roles.append("Domain Specialist")

    activities = [
        {
            "activity": "Signal Collection",
            "assignments": _raci_row(CONSULTED, INFORMED, RESPONSIBLE, roles),
        },
        {
            "activity": "Unit Prioritization",
            "assignments": _raci_row(RESPONSIBLE, CONSULTED, CONSULTED, roles),
        },
        {
            "activity": "Architecture Design",
            "assignments": _raci_row(INFORMED, RESPONSIBLE, INFORMED, roles),
        },
        {
            "activity": "Implementation",
            "assignments": _raci_row(INFORMED, ACCOUNTABLE, INFORMED, roles),
        },
        {
            "activity": "Quality Review",
            "assignments": _raci_row(ACCOUNTABLE, RESPONSIBLE, CONSULTED, roles),
        },
        {
            "activity": "Stakeholder Reporting",
            "assignments": _raci_row(RESPONSIBLE, CONSULTED, CONSULTED, roles),
        },
    ]

    return {"roles": roles, "activities": activities}


def _raci_row(product: str, tech: str, analyst: str, roles: list[str]) -> list[str]:
    """Build a RACI assignment row, padding for additional roles."""
    base = [product, tech, analyst]
    # Additional roles default to Informed
    while len(base) < len(roles):
        base.append(CONSULTED)
    return base


def _define_communication_norms(signals: list[Any]) -> dict[str, list[dict[str, str]]]:
    """Define communication channels and meeting cadences."""
    channels = [
        {"name": "Slack #team-product", "purpose": "Day-to-day communication and quick decisions"},
        {"name": "Email", "purpose": "Formal announcements and external stakeholder communication"},
        {"name": "Wiki/Docs", "purpose": "Persistent documentation, specs, and decision records"},
    ]

    meetings = [
        {"name": "Daily Standup", "frequency": "Daily", "purpose": "Progress updates and blocker resolution"},
        {"name": "Sprint Planning", "frequency": "Bi-weekly", "purpose": "Prioritize and scope upcoming work"},
        {"name": "Retrospective", "frequency": "Bi-weekly", "purpose": "Reflect on process and identify improvements"},
        {"name": "Strategy Review", "frequency": "Monthly", "purpose": "Review market intelligence and adjust priorities"},
    ]

    # Add signal review if signals exist
    if signals:
        meetings.append({
            "name": "Signal Review",
            "frequency": "Weekly",
            "purpose": "Triage new signals and update intelligence backlog",
        })

    return {"channels": channels, "meetings": meetings}


def _define_escalation_paths() -> list[dict[str, str]]:
    """Define escalation paths for issues."""
    return [
        {"level": "Level 1 — Team", "action": "Raise in daily standup or Slack channel"},
        {"level": "Level 2 — Lead", "action": "Escalate to Product or Tech Lead for decision"},
        {"level": "Level 3 — Management", "action": "Escalate to department head with impact analysis"},
        {"level": "Level 4 — Executive", "action": "Raise to executive sponsor with recommendation"},
    ]


def _define_decision_process() -> dict[str, Any]:
    """Define decision-making process."""
    return {
        "model": "Consent-based with RACI accountability",
        "steps": [
            "Proposal: Author writes decision proposal with context and options",
            "Review: RACI-designated roles review and provide input",
            "Decision: Accountable party makes final call with consent from consulted parties",
            "Record: Decision logged with rationale and expected outcomes",
            "Communicate: Informed parties notified of decision and implications",
        ],
    }
