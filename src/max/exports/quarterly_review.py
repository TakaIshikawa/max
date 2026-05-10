"""Quarterly business review (QBR) export.

Compiles quarterly metrics, goal progress, key achievements, and next
quarter priorities into structured markdown with data tables, trend
indicators, and narrative commentary.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.quarterly_review.v1"
KIND = "max.quarterly_review"

# Goal status indicators
STATUS_GREEN = "green"
STATUS_YELLOW = "yellow"
STATUS_RED = "red"

# Trend direction indicators
TREND_UP = "↑"
TREND_DOWN = "↓"
TREND_FLAT = "→"


def build_quarterly_review(
    store: Store,
    domain: str | None = None,
    *,
    quarter: str | None = None,
) -> dict[str, Any]:
    """Build quarterly business review from signals and buildable units.

    Args:
        store: Database store containing signals and buildable units.
        domain: Optional domain filter.
        quarter: Quarter label (e.g. 'Q1 2026'). Auto-generated if not given.

    Returns:
        Dict with QBR data including metrics, goals, achievements, and priorities.
    """
    units = store.get_buildable_units(limit=1000, domain=domain)
    signals = store.get_signals(limit=1000)

    if quarter is None:
        now = datetime.now(timezone.utc)
        q = (now.month - 1) // 3 + 1
        quarter = f"Q{q} {now.year}"

    metrics = _compile_metrics(units, signals)
    goals = _assess_goal_progress(units)
    achievements = _extract_achievements(units, signals)
    priorities = _extract_priorities(units, signals)
    comparisons = _build_quarter_comparisons(metrics)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "quarterly_review",
            "domain_filter": domain,
        },
        "quarter": quarter,
        "metrics": metrics,
        "goal_progress": goals,
        "key_achievements": achievements,
        "next_quarter_priorities": priorities,
        "quarter_comparisons": comparisons,
    }


def render_quarterly_review_markdown(report: dict[str, Any]) -> str:
    """Render quarterly review as Markdown."""
    lines = [
        f"# Quarterly Business Review — {report['quarter']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
    ]

    # Metrics table
    lines.extend(["## Key Metrics", ""])
    metrics = report["metrics"]
    if metrics:
        lines.extend([
            "| Metric | Value | Trend |",
            "|--------|-------|-------|",
        ])
        for m in metrics:
            lines.append(f"| {m['name']} | {m['value']} | {m['trend']} |")
        lines.append("")
    else:
        lines.extend(["- No metrics available", ""])

    # Goal progress
    lines.extend(["## Goal Progress", ""])
    goals = report["goal_progress"]
    if goals:
        for goal in goals:
            indicator = _status_emoji(goal["status"])
            lines.append(f"- {indicator} **{goal['goal']}** — {goal['progress']}")
        lines.append("")
    else:
        lines.extend(["- No goals tracked", ""])

    # Key achievements
    lines.extend(["## Key Achievements", ""])
    achievements = report["key_achievements"]
    if achievements:
        for ach in achievements:
            lines.append(f"- {ach}")
    else:
        lines.append("- No notable achievements this quarter")
    lines.append("")

    # Next quarter priorities
    lines.extend(["## Next Quarter Priorities", ""])
    priorities = report["next_quarter_priorities"]
    if priorities:
        for i, p in enumerate(priorities, 1):
            lines.append(f"{i}. {p}")
    else:
        lines.append("- No priorities defined")
    lines.append("")

    # Quarter comparisons
    lines.extend(["## Quarter-over-Quarter Comparison", ""])
    comparisons = report["quarter_comparisons"]
    if comparisons:
        lines.extend([
            "| Metric | Current | Previous | Change |",
            "|--------|---------|----------|--------|",
        ])
        for c in comparisons:
            lines.append(
                f"| {c['metric']} | {c['current']} | {c['previous']} | {c['change']} |"
            )
        lines.append("")
    else:
        lines.extend(["- No comparison data available", ""])

    return "\n".join(lines).rstrip() + "\n"


def render_quarterly_review_json(report: dict[str, Any]) -> str:
    """Render quarterly review as formatted JSON."""
    return json.dumps(report, indent=2, default=str)


# ── Internal helpers ─────────────────────────────────────────────────


def _status_emoji(status: str) -> str:
    """Return status indicator for goal progress."""
    return {
        STATUS_GREEN: "🟢",
        STATUS_YELLOW: "🟡",
        STATUS_RED: "🔴",
    }.get(status, "⚪")


def _compile_metrics(
    units: list[Any],
    signals: list[Any],
) -> list[dict[str, Any]]:
    """Compile key metrics from units and signals."""
    metrics: list[dict[str, Any]] = []

    # Signal volume metric
    metrics.append({
        "name": "Signals Collected",
        "value": len(signals),
        "trend": TREND_UP if len(signals) > 0 else TREND_FLAT,
    })

    # Buildable units metric
    metrics.append({
        "name": "Buildable Units",
        "value": len(units),
        "trend": TREND_UP if len(units) > 0 else TREND_FLAT,
    })

    # Average quality score
    if units:
        avg_quality = sum(getattr(u, "quality_score", 0.0) for u in units) / len(units)
        metrics.append({
            "name": "Avg Quality Score",
            "value": f"{avg_quality:.2f}",
            "trend": TREND_UP if avg_quality > 0.6 else TREND_DOWN if avg_quality < 0.4 else TREND_FLAT,
        })

    # Domain coverage
    domains = {getattr(u, "domain", "") for u in units} - {""}
    if domains:
        metrics.append({
            "name": "Domains Covered",
            "value": len(domains),
            "trend": TREND_FLAT,
        })

    # Source diversity
    source_types = {str(s.source_type) for s in signals}
    if source_types:
        metrics.append({
            "name": "Source Types",
            "value": len(source_types),
            "trend": TREND_FLAT,
        })

    return metrics


def _assess_goal_progress(units: list[Any]) -> list[dict[str, str]]:
    """Assess goal progress from unit statuses and quality scores."""
    goals: list[dict[str, str]] = []

    if not units:
        return goals

    # Quality goal
    avg_quality = sum(getattr(u, "quality_score", 0.0) for u in units) / len(units)
    if avg_quality >= 0.7:
        status = STATUS_GREEN
        progress = f"Average quality {avg_quality:.0%} — exceeds target"
    elif avg_quality >= 0.4:
        status = STATUS_YELLOW
        progress = f"Average quality {avg_quality:.0%} — approaching target"
    else:
        status = STATUS_RED
        progress = f"Average quality {avg_quality:.0%} — below target"
    goals.append({"goal": "Unit Quality", "status": status, "progress": progress})

    # Coverage goal
    domains = {getattr(u, "domain", "") for u in units} - {""}
    if len(domains) >= 3:
        goals.append({
            "goal": "Domain Coverage",
            "status": STATUS_GREEN,
            "progress": f"Covering {len(domains)} domains",
        })
    elif len(domains) >= 1:
        goals.append({
            "goal": "Domain Coverage",
            "status": STATUS_YELLOW,
            "progress": f"Covering {len(domains)} domain(s) — expand coverage",
        })

    # Volume goal
    if len(units) >= 10:
        goals.append({
            "goal": "Pipeline Volume",
            "status": STATUS_GREEN,
            "progress": f"{len(units)} units in pipeline",
        })
    elif len(units) >= 5:
        goals.append({
            "goal": "Pipeline Volume",
            "status": STATUS_YELLOW,
            "progress": f"{len(units)} units — increase throughput",
        })
    else:
        goals.append({
            "goal": "Pipeline Volume",
            "status": STATUS_RED,
            "progress": f"Only {len(units)} units — significantly below target",
        })

    return goals


def _extract_achievements(
    units: list[Any],
    signals: list[Any],
) -> list[str]:
    """Extract key achievements from high-quality units and signals."""
    achievements: list[str] = []

    # High-quality units as achievements
    high_quality = [u for u in units if getattr(u, "quality_score", 0.0) > 0.7]
    if high_quality:
        achievements.append(
            f"Identified {len(high_quality)} high-quality buildable units"
        )

    # Signal collection
    if signals:
        source_counter: Counter[str] = Counter()
        for s in signals:
            source_counter[str(s.source_type)] += 1
        top_source = source_counter.most_common(1)[0]
        achievements.append(
            f"Collected {len(signals)} signals across {len(source_counter)} source types "
            f"(top: {top_source[0]} with {top_source[1]})"
        )

    # Domain diversity
    domains = {getattr(u, "domain", "") for u in units} - {""}
    if domains:
        achievements.append(f"Coverage across {len(domains)} domain(s): {', '.join(sorted(domains))}")

    return achievements


def _extract_priorities(
    units: list[Any],
    signals: list[Any],
) -> list[str]:
    """Extract next quarter priorities from gaps and opportunities."""
    priorities: list[str] = []

    # Low-quality units need improvement
    low_quality = [u for u in units if getattr(u, "quality_score", 0.0) < 0.4]
    if low_quality:
        priorities.append(
            f"Improve quality for {len(low_quality)} below-threshold units"
        )

    # Expand signal sources
    source_types = {str(s.source_type) for s in signals}
    if len(source_types) < 3:
        priorities.append("Diversify signal source types for broader coverage")

    # Top-scoring units to advance
    top_units = sorted(
        units,
        key=lambda u: getattr(u, "quality_score", 0.0),
        reverse=True,
    )[:3]
    for unit in top_units:
        solution = getattr(unit, "solution", "")
        if solution:
            priorities.append(f"Advance: {solution}")

    if not priorities:
        priorities.append("Continue current trajectory and expand coverage")

    return priorities[:7]


def _build_quarter_comparisons(
    metrics: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build quarter-over-quarter comparison from current metrics.

    Since we only have current quarter data, the comparison shows
    placeholder previous values with the current as reference.
    """
    comparisons: list[dict[str, str]] = []

    for metric in metrics:
        comparisons.append({
            "metric": metric["name"],
            "current": str(metric["value"]),
            "previous": "N/A",
            "change": metric["trend"],
        })

    return comparisons
