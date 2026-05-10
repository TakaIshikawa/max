"""Technical debt tracking report export.

Tracks and prioritizes technical debt items by analyzing code complexity,
test coverage gaps, deprecated dependencies, and architectural issues.
Exports debt inventory with payoff prioritization.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.technical_debt_report.v1"
KIND = "max.technical_debt_report"

DEBT_CATEGORIES = ("complexity", "coverage", "dependency", "architecture")


def build_technical_debt_report(
    debt_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build technical debt report with scoring and prioritization.

    Args:
        debt_items: List of debt item dicts with keys:
            - name: str
            - category: str (complexity|coverage|dependency|architecture)
            - effort_hours: float (estimated hours to fix)
            - impact: int (1-5, business impact if not addressed)
            - description: str
            - affected_components: list[str]

    Returns:
        Technical debt report with scored items, prioritization, and payoff ratios.
    """
    scored = _score_debt_items(debt_items)
    prioritized = _prioritize_debt(scored)
    by_category = _group_by_category(scored)
    summary = _build_summary(scored)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "technical_debt_report",
        },
        "debt_items": scored,
        "prioritized": prioritized,
        "by_category": by_category,
        "summary": summary,
    }


def render_technical_debt_markdown(report: dict[str, Any]) -> str:
    """Render technical debt report as Markdown.

    Args:
        report: Technical debt report from build_technical_debt_report

    Returns:
        Markdown formatted report
    """
    lines = [
        "# Technical Debt Report",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Kind: `{report['kind']}`",
        "",
    ]

    # Summary
    summary = report["summary"]
    lines.extend([
        "## Summary",
        "",
        f"- Total debt items: {summary['total_items']}",
        f"- Total estimated effort: {summary['total_effort_hours']:.1f}h",
        f"- Average payoff ratio: {summary['avg_payoff_ratio']:.2f}",
        f"- Highest priority category: {summary['highest_priority_category']}",
        "",
    ])

    # Prioritized List
    lines.extend([
        "## Prioritized Debt Items",
        "",
        "| # | Item | Category | Effort | Impact | Payoff Ratio |",
        "|---|------|----------|--------|--------|--------------|",
    ])
    for i, item in enumerate(report["prioritized"], 1):
        lines.append(
            f"| {i} | {item['name']} | {item['category']} | "
            f"{item['effort_hours']:.0f}h | {item['impact']}/5 | "
            f"{item['payoff_ratio']:.2f} |"
        )
    lines.append("")

    # By Category
    lines.extend(["## Debt by Category", ""])
    for category, items in report["by_category"].items():
        if items:
            lines.extend([
                f"### {category.title()}",
                "",
            ])
            for item in items:
                lines.append(
                    f"- **{item['name']}**: {item['description']} "
                    f"(effort: {item['effort_hours']:.0f}h, payoff: {item['payoff_ratio']:.2f})"
                )
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _score_debt_items(debt_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score debt items by calculating payoff ratio (impact / effort)."""
    scored = []
    for item in debt_items:
        effort = item.get("effort_hours", 1)
        impact = item.get("impact", 1)
        # Payoff ratio: higher means more value per hour of effort
        payoff_ratio = impact / max(effort, 0.1)
        severity_score = impact * 5  # Scale to 25-point max
        scored.append({
            **item,
            "payoff_ratio": payoff_ratio,
            "severity_score": severity_score,
        })
    return scored


def _prioritize_debt(scored_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prioritize debt items by payoff ratio (highest first)."""
    return sorted(scored_items, key=lambda x: x["payoff_ratio"], reverse=True)


def _group_by_category(
    scored_items: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group debt items by category."""
    groups: dict[str, list[dict[str, Any]]] = {c: [] for c in DEBT_CATEGORIES}
    for item in scored_items:
        cat = item.get("category", "complexity")
        if cat in groups:
            groups[cat].append(item)
        else:
            groups["complexity"].append(item)
    return groups


def _build_summary(scored_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build summary statistics for the debt report."""
    if not scored_items:
        return {
            "total_items": 0,
            "total_effort_hours": 0.0,
            "avg_payoff_ratio": 0.0,
            "highest_priority_category": "none",
        }

    total_effort = sum(item.get("effort_hours", 0) for item in scored_items)
    avg_payoff = sum(item["payoff_ratio"] for item in scored_items) / len(scored_items)

    # Find category with highest average payoff ratio
    category_ratios: dict[str, list[float]] = {}
    for item in scored_items:
        cat = item.get("category", "complexity")
        if cat not in category_ratios:
            category_ratios[cat] = []
        category_ratios[cat].append(item["payoff_ratio"])

    highest_cat = max(
        category_ratios,
        key=lambda c: sum(category_ratios[c]) / len(category_ratios[c]),
    )

    return {
        "total_items": len(scored_items),
        "total_effort_hours": total_effort,
        "avg_payoff_ratio": avg_payoff,
        "highest_priority_category": highest_cat,
    }
