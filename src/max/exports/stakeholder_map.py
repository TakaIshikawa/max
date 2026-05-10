"""Stakeholder mapping export for project stakeholder analysis.

Visualizes project stakeholders, their interests, and influence levels.
Generates stakeholder matrix with engagement strategies.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.stakeholder_map.v1"
KIND = "max.stakeholder_map"

# Power/Interest quadrants
QUADRANT_HIGH_POWER_HIGH_INTEREST = "manage_closely"
QUADRANT_HIGH_POWER_LOW_INTEREST = "keep_satisfied"
QUADRANT_LOW_POWER_HIGH_INTEREST = "keep_informed"
QUADRANT_LOW_POWER_LOW_INTEREST = "monitor"


def build_stakeholder_map(
    stakeholders: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build stakeholder map with power/interest analysis and engagement strategies.

    Args:
        stakeholders: List of stakeholder dicts with keys:
            - name: str
            - role: str
            - interest: int (1-5, how interested in project outcomes)
            - influence: int (1-5, how much power over project)
            - sentiment: str (supportive|neutral|resistant)

    Returns:
        Stakeholder map with quadrant classifications and engagement strategies.
    """
    classified = _classify_stakeholders(stakeholders)
    quadrants = _group_by_quadrant(classified)
    strategies = _recommend_engagement_strategies(classified)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "project": "max",
            "entity_type": "stakeholder_map",
        },
        "stakeholders": classified,
        "quadrants": quadrants,
        "engagement_strategies": strategies,
        "summary": {
            "total_stakeholders": len(stakeholders),
            "manage_closely": len(quadrants.get(QUADRANT_HIGH_POWER_HIGH_INTEREST, [])),
            "keep_satisfied": len(quadrants.get(QUADRANT_HIGH_POWER_LOW_INTEREST, [])),
            "keep_informed": len(quadrants.get(QUADRANT_LOW_POWER_HIGH_INTEREST, [])),
            "monitor": len(quadrants.get(QUADRANT_LOW_POWER_LOW_INTEREST, [])),
        },
    }


def render_stakeholder_map_markdown(report: dict[str, Any]) -> str:
    """Render stakeholder map as Markdown.

    Args:
        report: Stakeholder map from build_stakeholder_map

    Returns:
        Markdown formatted report
    """
    lines = [
        "# Stakeholder Map",
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
        f"- Total stakeholders: {summary['total_stakeholders']}",
        f"- Manage closely (high power, high interest): {summary['manage_closely']}",
        f"- Keep satisfied (high power, low interest): {summary['keep_satisfied']}",
        f"- Keep informed (low power, high interest): {summary['keep_informed']}",
        f"- Monitor (low power, low interest): {summary['monitor']}",
        "",
    ])

    # Stakeholder Matrix
    lines.extend([
        "## Stakeholder Matrix",
        "",
        "| Name | Role | Interest | Influence | Quadrant | Sentiment |",
        "|------|------|----------|-----------|----------|-----------|",
    ])
    for s in report["stakeholders"]:
        lines.append(
            f"| {s['name']} | {s['role']} | {s['interest']} | "
            f"{s['influence']} | {s['quadrant']} | {s['sentiment']} |"
        )
    lines.append("")

    # Engagement Strategies
    lines.extend(["## Engagement Strategies", ""])
    for strategy in report["engagement_strategies"]:
        lines.extend([
            f"### {strategy['stakeholder']}",
            "",
            f"- **Quadrant**: {strategy['quadrant']}",
            f"- **Strategy**: {strategy['strategy']}",
            f"- **Communication frequency**: {strategy['communication_frequency']}",
            "",
        ])

    return "\n".join(lines).rstrip() + "\n"


def _classify_stakeholders(
    stakeholders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Classify stakeholders into power/interest quadrants."""
    classified = []
    for s in stakeholders:
        interest = s["interest"]
        influence = s["influence"]
        quadrant = _determine_quadrant(interest, influence)
        classified.append({**s, "quadrant": quadrant})
    return classified


def _determine_quadrant(interest: int, influence: int) -> str:
    """Determine power/interest quadrant based on scores."""
    high_influence = influence >= 4
    high_interest = interest >= 4

    if high_influence and high_interest:
        return QUADRANT_HIGH_POWER_HIGH_INTEREST
    elif high_influence and not high_interest:
        return QUADRANT_HIGH_POWER_LOW_INTEREST
    elif not high_influence and high_interest:
        return QUADRANT_LOW_POWER_HIGH_INTEREST
    else:
        return QUADRANT_LOW_POWER_LOW_INTEREST


def _group_by_quadrant(
    classified: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group classified stakeholders by quadrant."""
    quadrants: dict[str, list[dict[str, Any]]] = {}
    for s in classified:
        q = s["quadrant"]
        if q not in quadrants:
            quadrants[q] = []
        quadrants[q].append(s)
    return quadrants


def _recommend_engagement_strategies(
    classified: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recommend engagement strategies per stakeholder."""
    strategies = []
    for s in classified:
        quadrant = s["quadrant"]
        sentiment = s.get("sentiment", "neutral")
        strategy = _strategy_for_quadrant(quadrant, sentiment)
        frequency = _communication_frequency(quadrant)

        strategies.append({
            "stakeholder": s["name"],
            "quadrant": quadrant,
            "strategy": strategy,
            "communication_frequency": frequency,
        })
    return strategies


def _strategy_for_quadrant(quadrant: str, sentiment: str) -> str:
    """Generate engagement strategy based on quadrant and sentiment."""
    base_strategies = {
        QUADRANT_HIGH_POWER_HIGH_INTEREST: "Engage actively; involve in key decisions",
        QUADRANT_HIGH_POWER_LOW_INTEREST: "Keep satisfied with regular updates; avoid overwhelming",
        QUADRANT_LOW_POWER_HIGH_INTEREST: "Keep informed; leverage as advocates",
        QUADRANT_LOW_POWER_LOW_INTEREST: "Monitor with minimal effort",
    }
    strategy = base_strategies.get(quadrant, "Monitor")

    if sentiment == "resistant":
        strategy += "; address concerns proactively to reduce resistance"
    elif sentiment == "supportive":
        strategy += "; leverage support to build momentum"

    return strategy


def _communication_frequency(quadrant: str) -> str:
    """Determine communication frequency by quadrant."""
    frequencies = {
        QUADRANT_HIGH_POWER_HIGH_INTEREST: "weekly",
        QUADRANT_HIGH_POWER_LOW_INTEREST: "bi-weekly",
        QUADRANT_LOW_POWER_HIGH_INTEREST: "bi-weekly",
        QUADRANT_LOW_POWER_LOW_INTEREST: "monthly",
    }
    return frequencies.get(quadrant, "monthly")
