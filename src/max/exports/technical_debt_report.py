"""Technical debt tracking report export.

Tracks and prioritizes technical debt items by analyzing code complexity,
test coverage gaps, deprecated dependencies, and architectural issues.
Exports debt inventory with payoff prioritization.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.technical_debt_report.v1"
KIND = "max.technical_debt_report"

VALID_CATEGORIES = {
    "code_complexity",
    "test_coverage",
    "deprecated_dependency",
    "architecture",
}

SEVERITY_LEVELS = ("low", "medium", "high", "critical")
_SEVERITY_SCORES = {level: i + 1 for i, level in enumerate(SEVERITY_LEVELS)}


def compute_payoff_ratio(impact: float, effort: float) -> float:
    """Compute debt payoff ratio (impact / effort).

    Higher values indicate better return on investment for addressing the debt.

    Args:
        impact: Business impact score 0.0–1.0.
        effort: Effort to resolve 0.0–1.0 (1.0 = highest effort).

    Returns:
        Payoff ratio; higher is better. Returns 0.0 if effort is zero.
    """
    if effort <= 0:
        return 0.0
    return round(impact / effort, 2)


def _validate_debt_item(item: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a debt item."""
    category = item.get("category", "code_complexity")
    if category not in VALID_CATEGORIES:
        category = "code_complexity"

    severity = item.get("severity", "medium")
    if severity not in _SEVERITY_SCORES:
        severity = "medium"

    impact = max(0.0, min(1.0, float(item.get("impact", 0.5))))
    effort = max(0.0, min(1.0, float(item.get("effort", 0.5))))
    payoff = compute_payoff_ratio(impact, effort)

    return {
        "title": item.get("title", "Untitled Debt"),
        "description": item.get("description", ""),
        "category": category,
        "severity": severity,
        "severity_score": _SEVERITY_SCORES[severity],
        "impact": impact,
        "effort": effort,
        "payoff_ratio": payoff,
        "location": item.get("location", ""),
    }


def build_debt_report(
    items: list[dict[str, Any]],
    *,
    project_name: str = "Project",
) -> dict[str, Any]:
    """Build a technical debt report document.

    Args:
        items: List of debt item dicts, each containing:
            - title: str
            - description: str (optional)
            - category: str (code_complexity|test_coverage|deprecated_dependency|architecture)
            - severity: str (low|medium|high|critical)
            - impact: float 0.0–1.0 (business impact)
            - effort: float 0.0–1.0 (effort to resolve)
            - location: str (optional, file/module reference)
        project_name: Name of the project.

    Returns:
        Structured technical debt report document dict.
    """
    validated = [_validate_debt_item(i) for i in items]

    # Sort by payoff ratio descending (best ROI first)
    prioritized = sorted(validated, key=lambda d: d["payoff_ratio"], reverse=True)

    by_category: dict[str, list[dict[str, Any]]] = {c: [] for c in VALID_CATEGORIES}
    for d in validated:
        by_category[d["category"]].append(d)

    total_impact = sum(d["impact"] for d in validated)
    total_effort = sum(d["effort"] for d in validated)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_name": project_name,
        "items": prioritized,
        "by_category": by_category,
        "summary": {
            "total_items": len(validated),
            "total_impact": round(total_impact, 2),
            "total_effort": round(total_effort, 2),
            "by_severity": {
                level: len([d for d in validated if d["severity"] == level])
                for level in SEVERITY_LEVELS
            },
            "by_category": {
                cat: len(members) for cat, members in by_category.items()
            },
        },
    }


def render_debt_markdown(document: dict[str, Any]) -> str:
    """Render technical debt report as markdown.

    Args:
        document: Debt report document from build_debt_report.

    Returns:
        Markdown formatted debt report.
    """
    lines = [
        f"# Technical Debt Report — {document['project_name']}",
        "",
        "## Summary",
        "",
    ]

    summary = document["summary"]
    lines.append(f"Total debt items: {summary['total_items']}")
    lines.append(f"Total impact: {summary['total_impact']}")
    lines.append(f"Total effort: {summary['total_effort']}")
    lines.append("")

    lines.append("### By Severity")
    lines.append("")
    for level in SEVERITY_LEVELS:
        count = summary["by_severity"].get(level, 0)
        lines.append(f"- **{level.capitalize()}**: {count}")
    lines.append("")

    # Prioritized items
    lines.append("## Prioritized Debt Items")
    lines.append("")
    lines.append("*Ordered by payoff ratio (impact / effort), highest first.*")
    lines.append("")

    for item in document["items"]:
        lines.extend(_render_debt_entry(item))

    # By category
    category_labels = {
        "code_complexity": "Code Complexity",
        "test_coverage": "Test Coverage Gaps",
        "deprecated_dependency": "Deprecated Dependencies",
        "architecture": "Architectural Issues",
    }
    by_cat = document.get("by_category", {})
    for cat_key, label in category_labels.items():
        members = by_cat.get(cat_key, [])
        if not members:
            continue
        lines.append(f"## {label}")
        lines.append("")
        for item in members:
            lines.append(f"- {item['title']} (payoff: {item['payoff_ratio']})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_debt_entry(item: dict[str, Any]) -> list[str]:
    """Render a single debt item as markdown lines."""
    lines = [
        f"### {item['title']}",
        "",
        f"- **Category**: {item['category']}",
        f"- **Severity**: {item['severity']}",
        f"- **Impact**: {item['impact']}",
        f"- **Effort**: {item['effort']}",
        f"- **Payoff ratio**: {item['payoff_ratio']}",
    ]
    if item.get("description"):
        lines.append(f"- **Description**: {item['description']}")
    if item.get("location"):
        lines.append(f"- **Location**: {item['location']}")
    lines.append("")
    return lines


def render_debt_json(document: dict[str, Any]) -> str:
    """Render technical debt report as formatted JSON."""
    return json.dumps(document, indent=2, default=str)
