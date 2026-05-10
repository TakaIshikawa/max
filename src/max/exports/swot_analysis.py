"""SWOT analysis export — structured strategic analysis.

Generates strengths, weaknesses, opportunities, and threats analysis
with strategic implications and recommended actions per quadrant.
Supports weighted scoring of SWOT items by impact.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.swot_analysis.v1"
KIND = "max.swot_analysis"

_QUADRANTS = ("strengths", "weaknesses", "opportunities", "threats")


# ── Public API ───────────────────────────────────────────────────────


def build_swot_analysis(
    *,
    subject: str,
    strengths: list[dict[str, Any]] | None = None,
    weaknesses: list[dict[str, Any]] | None = None,
    opportunities: list[dict[str, Any]] | None = None,
    threats: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a SWOT analysis document.

    Args:
        subject: Name of the product, project, or company being analyzed.
        strengths: List of dicts with 'description', optional 'impact'
            (1-5), 'implication', and 'action'.
        weaknesses: Same structure as strengths.
        opportunities: Same structure as strengths.
        threats: Same structure as strengths.

    Returns:
        Dict with four quadrants, weighted scores, and strategic
        recommendations.

    Raises:
        ValueError: If subject is empty or impact scores are out of range.
    """
    _validate_inputs(
        subject=subject,
        strengths=strengths,
        weaknesses=weaknesses,
        opportunities=opportunities,
        threats=threats,
    )

    scored = {
        "strengths": _score_items(strengths or []),
        "weaknesses": _score_items(weaknesses or []),
        "opportunities": _score_items(opportunities or []),
        "threats": _score_items(threats or []),
    }

    summary_scores = _compute_summary_scores(scored)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "swot_analysis",
        },
        "subject": subject,
        "quadrants": scored,
        "summary_scores": summary_scores,
    }


def render_swot_analysis_markdown(report: dict[str, Any]) -> str:
    """Render SWOT analysis as Markdown."""
    lines = [
        f"# SWOT Analysis: {report['subject']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
    ]

    labels = {
        "strengths": "Strengths",
        "weaknesses": "Weaknesses",
        "opportunities": "Opportunities",
        "threats": "Threats",
    }

    for quad in _QUADRANTS:
        items = report["quadrants"][quad]
        lines.extend([f"## {labels[quad]}", ""])
        if items:
            for item in items:
                lines.append(
                    f"- **[{item['impact']}/5]** {item['description']}"
                )
                if item.get("implication"):
                    lines.append(f"  - *Implication:* {item['implication']}")
                if item.get("action"):
                    lines.append(f"  - *Action:* {item['action']}")
            lines.append("")
        else:
            lines.extend(["- None identified.", ""])

    # Summary scores
    ss = report["summary_scores"]
    lines.extend([
        "## Summary Scores",
        "",
        f"- **Strengths total**: {ss['strengths_total']:.1f}",
        f"- **Weaknesses total**: {ss['weaknesses_total']:.1f}",
        f"- **Opportunities total**: {ss['opportunities_total']:.1f}",
        f"- **Threats total**: {ss['threats_total']:.1f}",
        f"- **Internal balance** (S - W): {ss['internal_balance']:.1f}",
        f"- **External balance** (O - T): {ss['external_balance']:.1f}",
        "",
    ])

    return "\n".join(lines).rstrip() + "\n"


def render_swot_analysis_json(report: dict[str, Any]) -> str:
    """Render SWOT analysis as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _validate_inputs(
    *,
    subject: str,
    strengths: list[dict[str, Any]] | None,
    weaknesses: list[dict[str, Any]] | None,
    opportunities: list[dict[str, Any]] | None,
    threats: list[dict[str, Any]] | None,
) -> None:
    """Validate SWOT inputs."""
    if not subject or not subject.strip():
        raise ValueError("subject must be a non-empty string")
    for quad_name, items in [
        ("strengths", strengths),
        ("weaknesses", weaknesses),
        ("opportunities", opportunities),
        ("threats", threats),
    ]:
        if items is None:
            continue
        for item in items:
            if "description" not in item:
                raise ValueError(
                    f"each {quad_name} item must have a 'description'"
                )
            impact = item.get("impact", 3)
            if not (1 <= impact <= 5):
                raise ValueError(
                    f"impact score must be 1-5, got {impact} in {quad_name}"
                )


def _score_items(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize and score SWOT items, sorted by impact descending."""
    result: list[dict[str, Any]] = []
    for item in items:
        result.append({
            "description": item["description"],
            "impact": item.get("impact", 3),
            "implication": item.get("implication", ""),
            "action": item.get("action", ""),
        })
    result.sort(key=lambda x: x["impact"], reverse=True)
    return result


def _compute_summary_scores(
    scored: dict[str, list[dict[str, Any]]],
) -> dict[str, float]:
    """Compute aggregate scores per quadrant and balance metrics."""
    def _total(quad: str) -> float:
        return sum(item["impact"] for item in scored[quad])

    s = _total("strengths")
    w = _total("weaknesses")
    o = _total("opportunities")
    t = _total("threats")

    return {
        "strengths_total": s,
        "weaknesses_total": w,
        "opportunities_total": o,
        "threats_total": t,
        "internal_balance": s - w,
        "external_balance": o - t,
    }
