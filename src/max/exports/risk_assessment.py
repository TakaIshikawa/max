"""Risk assessment report export.

Generates comprehensive project risk analysis with severity/probability scoring.
Categorizes risks into technical, resource, timeline, and dependency types.
Includes mitigation strategies for high-priority risks.
Exports to markdown and structured JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.risk_assessment.v1"
KIND = "max.risk_assessment"

VALID_CATEGORIES = {"technical", "resource", "timeline", "dependency"}
SEVERITY_LEVELS = ("low", "medium", "high", "critical")
PROBABILITY_LEVELS = ("unlikely", "possible", "likely", "almost_certain")

_SEVERITY_SCORES = {level: i + 1 for i, level in enumerate(SEVERITY_LEVELS)}
_PROBABILITY_SCORES = {level: i + 1 for i, level in enumerate(PROBABILITY_LEVELS)}


def compute_risk_score(severity: str, probability: str) -> int:
    """Compute a risk score (1–16) from severity and probability.

    Args:
        severity: One of SEVERITY_LEVELS.
        probability: One of PROBABILITY_LEVELS.

    Returns:
        Integer risk score.
    """
    s = _SEVERITY_SCORES.get(severity, 1)
    p = _PROBABILITY_SCORES.get(probability, 1)
    return s * p


def risk_priority(score: int) -> str:
    """Map a risk score to a priority label."""
    if score >= 9:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _validate_risk(risk: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a risk entry."""
    category = risk.get("category", "technical")
    if category not in VALID_CATEGORIES:
        category = "technical"

    severity = risk.get("severity", "medium")
    if severity not in _SEVERITY_SCORES:
        severity = "medium"

    probability = risk.get("probability", "possible")
    if probability not in _PROBABILITY_SCORES:
        probability = "possible"

    score = compute_risk_score(severity, probability)

    return {
        "title": risk.get("title", "Untitled Risk"),
        "description": risk.get("description", ""),
        "category": category,
        "severity": severity,
        "probability": probability,
        "score": score,
        "priority": risk_priority(score),
        "mitigation": risk.get("mitigation", ""),
    }


def build_risk_assessment(
    risks: list[dict[str, Any]],
    *,
    project_name: str = "Project",
) -> dict[str, Any]:
    """Build a risk assessment document.

    Args:
        risks: List of risk dicts, each containing:
            - title: str
            - description: str (optional)
            - category: str (technical|resource|timeline|dependency)
            - severity: str (low|medium|high|critical)
            - probability: str (unlikely|possible|likely|almost_certain)
            - mitigation: str (optional)
        project_name: Name of the project.

    Returns:
        Structured risk assessment document dict.
    """
    validated = [_validate_risk(r) for r in risks]
    validated.sort(key=lambda r: r["score"], reverse=True)

    by_category: dict[str, list[dict[str, Any]]] = {c: [] for c in VALID_CATEGORIES}
    for r in validated:
        by_category[r["category"]].append(r)

    high_priority = [r for r in validated if r["priority"] == "high"]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "risks": validated,
        "by_category": by_category,
        "high_priority_risks": high_priority,
        "summary": {
            "total": len(validated),
            "high": len([r for r in validated if r["priority"] == "high"]),
            "medium": len([r for r in validated if r["priority"] == "medium"]),
            "low": len([r for r in validated if r["priority"] == "low"]),
        },
    }


def render_risk_markdown(document: dict[str, Any]) -> str:
    """Render risk assessment as markdown.

    Args:
        document: Risk assessment document from build_risk_assessment.

    Returns:
        Markdown formatted risk report.
    """
    lines = [
        f"# Risk Assessment — {document['project_name']}",
        "",
        "## Summary",
        "",
    ]

    summary = document["summary"]
    lines.append(f"Total risks identified: {summary['total']}")
    lines.append("")
    lines.append(f"- **High priority**: {summary['high']}")
    lines.append(f"- **Medium priority**: {summary['medium']}")
    lines.append(f"- **Low priority**: {summary['low']}")
    lines.append("")

    # High priority section
    high = document.get("high_priority_risks", [])
    if high:
        lines.append("## High Priority Risks")
        lines.append("")
        for r in high:
            lines.extend(_render_risk_entry(r))

    # By category
    category_labels = {
        "technical": "Technical Risks",
        "resource": "Resource Risks",
        "timeline": "Timeline Risks",
        "dependency": "Dependency Risks",
    }
    by_cat = document.get("by_category", {})
    for cat_key, label in category_labels.items():
        members = by_cat.get(cat_key, [])
        if not members:
            continue
        lines.append(f"## {label}")
        lines.append("")
        for r in members:
            lines.extend(_render_risk_entry(r))

    return "\n".join(lines).rstrip() + "\n"


def _render_risk_entry(risk: dict[str, Any]) -> list[str]:
    """Render a single risk entry as markdown lines."""
    lines = [
        f"### {risk['title']}",
        "",
        f"- **Severity**: {risk['severity']}",
        f"- **Probability**: {risk['probability']}",
        f"- **Score**: {risk['score']}",
        f"- **Priority**: {risk['priority']}",
    ]
    if risk.get("description"):
        lines.append(f"- **Description**: {risk['description']}")
    if risk.get("mitigation"):
        lines.append(f"- **Mitigation**: {risk['mitigation']}")
    lines.append("")
    return lines


def render_risk_json(document: dict[str, Any]) -> str:
    """Render risk assessment as formatted JSON."""
    return json.dumps(document, indent=2, default=str)
