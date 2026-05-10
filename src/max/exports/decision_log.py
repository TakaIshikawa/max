"""Decision log export for architectural and business choices.

Captures decision context, options considered, rationale, consequences,
and status. Exports chronological decision log with cross-references
to related ADRs and specs.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.decision_log.v1"
KIND = "max.decision_log"

# Decision statuses
STATUS_PROPOSED = "proposed"
STATUS_ACCEPTED = "accepted"
STATUS_DEPRECATED = "deprecated"
STATUS_SUPERSEDED = "superseded"

VALID_STATUSES = (STATUS_PROPOSED, STATUS_ACCEPTED, STATUS_DEPRECATED, STATUS_SUPERSEDED)


def build_decision_log(
    store: Store,
    domain: str | None = None,
) -> dict[str, Any]:
    """Build decision log from signals and buildable units.

    Args:
        store: Database store containing signals and buildable units.
        domain: Optional domain filter.

    Returns:
        Dict with schema metadata and chronological decision entries.
    """
    units = store.get_buildable_units(limit=1000, domain=domain)

    decisions = _extract_decisions(units)
    summary = _build_summary(decisions)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "decision_log",
            "domain_filter": domain,
        },
        "decision_count": len(decisions),
        "decisions": decisions,
        "summary": summary,
    }


def render_decision_log_markdown(report: dict[str, Any]) -> str:
    """Render decision log as Markdown."""
    lines = [
        "# Decision Log",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Total decisions: {report['decision_count']}",
        "",
    ]

    # Summary
    summary = report["summary"]
    lines.extend(["## Summary", ""])
    for status, count in summary.get("status_counts", {}).items():
        lines.append(f"- **{status.title()}**: {count}")
    lines.append("")

    # Decisions
    lines.extend(["## Decisions", ""])
    if report["decisions"]:
        for decision in report["decisions"]:
            lines.extend(_render_decision_markdown(decision))
    else:
        lines.extend(["- No decisions recorded", ""])

    return "\n".join(lines).rstrip() + "\n"


def render_decision_log_json(report: dict[str, Any]) -> str:
    """Render decision log as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _extract_decisions(
    units: list[Any],
) -> list[dict[str, Any]]:
    """Extract decision entries from units and signals."""
    decisions: list[dict[str, Any]] = []

    for unit in units:
        solution = getattr(unit, "solution", "")
        problem = getattr(unit, "problem", "")
        if not solution:
            continue

        # Determine status from quality
        quality = getattr(unit, "quality_score", 0.0)
        if quality > 0.7:
            status = STATUS_ACCEPTED
        elif quality > 0.4:
            status = STATUS_PROPOSED
        else:
            status = STATUS_PROPOSED

        # Build options from available data
        options = _build_options(unit)

        # Collect evidence signal IDs
        evidence_ids = getattr(unit, "evidence_signals", [])

        decision = {
            "id": f"DEC-{len(decisions) + 1:03d}",
            "title": solution,
            "context": problem or "Decision context derived from analysis",
            "status": status,
            "options": options,
            "chosen_option": solution,
            "rationale": getattr(unit, "value_proposition", "") or "Best available option based on analysis",
            "consequences": _infer_consequences(unit),
            "domain": getattr(unit, "domain", ""),
            "evidence_signals": list(evidence_ids),
            "date": datetime.now(timezone.utc).isoformat(),
        }
        decisions.append(decision)

    return decisions


def _build_options(unit: Any) -> list[dict[str, Any]]:
    """Build options considered for a decision."""
    options: list[dict[str, Any]] = []
    solution = getattr(unit, "solution", "")

    # The chosen option
    if solution:
        options.append({
            "name": solution,
            "pros": [
                getattr(unit, "value_proposition", "") or "Addresses identified need",
            ],
            "cons": ["Requires implementation investment"],
            "selected": True,
        })

    # Alternative: current workaround
    workaround = getattr(unit, "current_workaround", "")
    if workaround:
        options.append({
            "name": f"Continue with: {workaround}",
            "pros": ["No additional investment needed"],
            "cons": ["Does not fully address the problem"],
            "selected": False,
        })

    # Alternative: do nothing
    if solution:
        options.append({
            "name": "Do nothing",
            "pros": ["Zero cost and effort"],
            "cons": ["Problem persists", "Opportunity cost"],
            "selected": False,
        })

    return options


def _infer_consequences(unit: Any) -> list[str]:
    """Infer consequences of a decision from unit attributes."""
    consequences: list[str] = []

    vp = getattr(unit, "value_proposition", "")
    if vp:
        consequences.append(f"Expected benefit: {vp}")

    domain = getattr(unit, "domain", "")
    if domain:
        consequences.append(f"Affects {domain} domain")

    target = getattr(unit, "target_users", "")
    if target:
        consequences.append(f"Impacts {target} users")

    if not consequences:
        consequences.append("Impact to be assessed during implementation")

    return consequences


def _build_summary(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Build summary statistics for the decision log."""
    status_counts: dict[str, int] = defaultdict(int)
    domains: set[str] = set()

    for d in decisions:
        status_counts[d["status"]] += 1
        if d.get("domain"):
            domains.add(d["domain"])

    return {
        "status_counts": dict(status_counts),
        "domains": sorted(domains),
        "total": len(decisions),
    }


def _render_decision_markdown(decision: dict[str, Any]) -> list[str]:
    """Render a single decision entry as markdown."""
    lines: list[str] = []

    lines.extend([
        f"### {decision['id']}: {decision['title']}",
        "",
        f"**Status**: {decision['status'].title()}",
        f"**Domain**: {decision.get('domain', 'N/A')}",
        f"**Date**: {decision['date']}",
        "",
        "**Context**:",
        decision["context"],
        "",
    ])

    # Options
    lines.append("**Options Considered**:")
    lines.append("")
    for opt in decision.get("options", []):
        selected = " ✓" if opt.get("selected") else ""
        lines.append(f"- **{opt['name']}**{selected}")
        for pro in opt.get("pros", []):
            lines.append(f"  - Pro: {pro}")
        for con in opt.get("cons", []):
            lines.append(f"  - Con: {con}")
    lines.append("")

    # Rationale
    lines.extend([
        "**Rationale**:",
        decision["rationale"],
        "",
    ])

    # Consequences
    lines.append("**Consequences**:")
    lines.append("")
    for c in decision.get("consequences", []):
        lines.append(f"- {c}")
    lines.append("")

    return lines
