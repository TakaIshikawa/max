"""Risk assessment report export for project risk analysis.

Evaluates technical risks, resource constraints, timeline risks, and dependency
risks. Exports to markdown and JSON formats with mitigation strategies.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.risk_assessment.v1"
KIND = "max.risk_assessment"

RISK_CATEGORIES = ("technical", "resource", "timeline", "dependency")


def build_risk_assessment_report(
    risks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build risk assessment report with risk matrix and mitigation strategies.

    Args:
        risks: List of risk dicts with keys:
            - name: str
            - category: str (technical|resource|timeline|dependency)
            - severity: int (1-5)
            - probability: int (1-5)
            - description: str
            - mitigation: str | None

    Returns:
        Risk assessment report with matrix, categorized risks, and mitigations.
    """
    scored_risks = _score_risks(risks)
    categorized = _categorize_risks(scored_risks)
    matrix = _build_risk_matrix(scored_risks)
    high_priority = _get_high_priority_risks(scored_risks)
    mitigations = _generate_mitigations(high_priority)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "risk_assessment",
        },
        "risk_matrix": matrix,
        "categorized_risks": categorized,
        "high_priority_risks": high_priority,
        "mitigation_strategies": mitigations,
        "summary": {
            "total_risks": len(risks),
            "critical_count": len([r for r in scored_risks if r["risk_score"] >= 20]),
            "high_count": len([r for r in scored_risks if 12 <= r["risk_score"] < 20]),
            "medium_count": len([r for r in scored_risks if 6 <= r["risk_score"] < 12]),
            "low_count": len([r for r in scored_risks if r["risk_score"] < 6]),
        },
    }


def render_risk_assessment_markdown(report: dict[str, Any]) -> str:
    """Render risk assessment report as Markdown.

    Args:
        report: Risk assessment report from build_risk_assessment_report

    Returns:
        Markdown formatted report
    """
    lines = [
        "# Risk Assessment Report",
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
        f"- Total risks identified: {summary['total_risks']}",
        f"- Critical: {summary['critical_count']}",
        f"- High: {summary['high_count']}",
        f"- Medium: {summary['medium_count']}",
        f"- Low: {summary['low_count']}",
        "",
    ])

    # Risk Matrix
    lines.extend([
        "## Risk Matrix",
        "",
        "| Risk | Category | Severity | Probability | Score | Level |",
        "|------|----------|----------|-------------|-------|-------|",
    ])
    for entry in report["risk_matrix"]:
        lines.append(
            f"| {entry['name']} | {entry['category']} | "
            f"{entry['severity']} | {entry['probability']} | "
            f"{entry['risk_score']} | {entry['risk_level']} |"
        )
    lines.append("")

    # High Priority Risks
    if report["high_priority_risks"]:
        lines.extend(["## High Priority Risks", ""])
        for risk in report["high_priority_risks"]:
            lines.extend([
                f"### {risk['name']}",
                "",
                f"- **Category**: {risk['category']}",
                f"- **Score**: {risk['risk_score']} ({risk['risk_level']})",
                f"- **Description**: {risk['description']}",
                "",
            ])

    # Mitigation Strategies
    if report["mitigation_strategies"]:
        lines.extend(["## Mitigation Strategies", ""])
        for m in report["mitigation_strategies"]:
            lines.extend([
                f"### {m['risk_name']}",
                "",
                f"- **Strategy**: {m['strategy']}",
                f"- **Priority**: {m['priority']}",
                "",
            ])

    return "\n".join(lines).rstrip() + "\n"


def _score_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score risks by multiplying severity and probability."""
    scored = []
    for risk in risks:
        score = risk["severity"] * risk["probability"]
        level = _risk_level(score)
        scored.append({**risk, "risk_score": score, "risk_level": level})
    scored.sort(key=lambda r: r["risk_score"], reverse=True)
    return scored


def _risk_level(score: int) -> str:
    """Determine risk level from score."""
    if score >= 20:
        return "critical"
    elif score >= 12:
        return "high"
    elif score >= 6:
        return "medium"
    return "low"


def _categorize_risks(
    scored_risks: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Categorize risks by type."""
    categorized: dict[str, list[dict[str, Any]]] = {c: [] for c in RISK_CATEGORIES}
    for risk in scored_risks:
        cat = risk.get("category", "technical")
        if cat in categorized:
            categorized[cat].append(risk)
        else:
            categorized["technical"].append(risk)
    return categorized


def _build_risk_matrix(scored_risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build risk matrix sorted by score descending."""
    return [
        {
            "name": r["name"],
            "category": r["category"],
            "severity": r["severity"],
            "probability": r["probability"],
            "risk_score": r["risk_score"],
            "risk_level": r["risk_level"],
        }
        for r in scored_risks
    ]


def _get_high_priority_risks(scored_risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Get risks with score >= 12 (high and critical)."""
    return [r for r in scored_risks if r["risk_score"] >= 12]


def _generate_mitigations(
    high_priority_risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate mitigation strategies for high-priority risks."""
    mitigations = []
    for risk in high_priority_risks:
        # Use provided mitigation or generate a default
        strategy = risk.get("mitigation") or _default_mitigation(risk)
        priority = "immediate" if risk["risk_score"] >= 20 else "high"
        mitigations.append({
            "risk_name": risk["name"],
            "strategy": strategy,
            "priority": priority,
            "risk_score": risk["risk_score"],
        })
    return mitigations


def _default_mitigation(risk: dict[str, Any]) -> str:
    """Generate default mitigation based on category."""
    defaults = {
        "technical": "Conduct technical spike to reduce uncertainty; add fallback approach",
        "resource": "Cross-train team members; identify backup resources",
        "timeline": "Add buffer time; identify scope reduction options",
        "dependency": "Identify alternatives; establish SLAs with dependency owners",
    }
    return defaults.get(risk.get("category", ""), "Assess and monitor risk regularly")
