"""Source budget rebalance plan from yield, error, cost, and strategy signals."""

from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "max.source_budget_rebalance_plan.v1"
KIND = "max.source_budget_rebalance_plan"


def build_source_budget_rebalance_plan(sources: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Recommend deterministic source budget changes from observed source performance."""

    rows = [_source_row(source, index) for index, source in enumerate(sources)]
    rows.sort(
        key=lambda row: (
            _direction_order(row["recommendation"]),
            -float(row["priority_score"]),
            str(row["source"]),
        )
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "source_count": len(rows),
            "increase_count": sum(1 for row in rows if row["recommendation"] == "increase"),
            "hold_count": sum(1 for row in rows if row["recommendation"] == "hold"),
            "reduce_count": sum(1 for row in rows if row["recommendation"] == "reduce"),
            "pause_count": sum(1 for row in rows if row["recommendation"] == "pause"),
        },
        "rebalance_rows": rows,
        "guardrails": [
            "Do not increase a source with unresolved data quality incidents.",
            "Keep at least one independent corroborating source for every critical evidence topic.",
        ],
    }


def render_source_budget_rebalance_plan_markdown(plan: Mapping[str, Any]) -> str:
    """Render a source budget rebalance plan as deterministic Markdown."""

    summary = plan["summary"]
    lines = [
        "# Source Budget Rebalance Plan",
        "",
        f"Schema: `{plan['schema_version']}`",
        f"Sources analyzed: {summary['source_count']}",
        "",
        "## Recommendation Summary",
        "",
        f"- Increase: {summary['increase_count']}",
        f"- Hold: {summary['hold_count']}",
        f"- Reduce: {summary['reduce_count']}",
        f"- Pause: {summary['pause_count']}",
        "",
        "## Source Recommendations",
        "",
    ]

    rows = list(plan.get("rebalance_rows", []))
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"### {row['source']}",
                    "",
                    f"- Current budget: {row['current_budget']:.2f}",
                    f"- Recommended budget direction: {row['recommendation']}",
                    f"- Reason: {row['reason']}",
                    f"- Guardrail note: {row['guardrail_note']}",
                    "",
                ]
            )
    else:
        lines.append("No source budget inputs were provided.")

    lines.extend(["## Guardrails", ""])
    lines.extend(f"- {item}" for item in plan.get("guardrails", []))
    return "\n".join(lines).rstrip() + "\n"


def _source_row(source: Mapping[str, Any], index: int) -> dict[str, Any]:
    name = _clean(source.get("source") or source.get("name") or source.get("id") or f"source-{index + 1}")
    current_budget = _nonnegative_float(source.get("current_budget", source.get("budget", 0.0)))
    observed_yield = _nonnegative_float(source.get("observed_yield", source.get("yield", 0.0)))
    cost = _nonnegative_float(source.get("cost", source.get("spend", current_budget)))
    error_rate = _bounded_float(source.get("error_rate", source.get("recent_error_rate", 0.0)))
    strategic_weight = _bounded_float(source.get("strategic_weight", source.get("weight", 0.5)))
    yield_per_cost = round(observed_yield / cost, 4) if cost > 0 else round(observed_yield, 4)
    performance_score = round((yield_per_cost * 0.55) + (strategic_weight * 0.35) - (error_rate * 0.45), 4)
    recommendation = _recommendation(yield_per_cost, error_rate, strategic_weight, performance_score)

    return {
        "source": name,
        "current_budget": round(current_budget, 2),
        "observed_yield": round(observed_yield, 4),
        "cost": round(cost, 2),
        "yield_per_cost": yield_per_cost,
        "error_rate": error_rate,
        "strategic_weight": strategic_weight,
        "performance_score": performance_score,
        "recommendation": recommendation,
        "priority_score": _priority_score(recommendation, performance_score, error_rate, strategic_weight),
        "reason": _reason(recommendation, yield_per_cost, error_rate, strategic_weight),
        "guardrail_note": _guardrail_note(recommendation, error_rate, strategic_weight),
    }


def _recommendation(
    yield_per_cost: float,
    error_rate: float,
    strategic_weight: float,
    performance_score: float,
) -> str:
    if error_rate >= 0.45 and strategic_weight < 0.75:
        return "pause"
    if error_rate >= 0.3:
        return "reduce"
    if yield_per_cost >= 2.0 and strategic_weight >= 0.55 and error_rate <= 0.15:
        return "increase"
    if performance_score < 0.45 and strategic_weight < 0.7:
        return "reduce"
    return "hold"


def _reason(recommendation: str, yield_per_cost: float, error_rate: float, strategic_weight: float) -> str:
    if recommendation == "increase":
        return (
            f"high yield per cost ({yield_per_cost:.2f}) with low recent error rate "
            f"({error_rate:.2f}) and strategic weight {strategic_weight:.2f}"
        )
    if recommendation == "pause":
        return (
            f"recent error rate {error_rate:.2f} is too high for the current strategic weight "
            f"({strategic_weight:.2f})"
        )
    if recommendation == "reduce":
        return (
            f"yield per cost {yield_per_cost:.2f} does not offset recent error rate "
            f"{error_rate:.2f} at strategic weight {strategic_weight:.2f}"
        )
    return (
        f"yield per cost {yield_per_cost:.2f}, recent error rate {error_rate:.2f}, "
        f"and strategic weight {strategic_weight:.2f} are within hold thresholds"
    )


def _guardrail_note(recommendation: str, error_rate: float, strategic_weight: float) -> str:
    if recommendation == "increase":
        return "cap increases until a second source confirms the added evidence yield"
    if recommendation == "pause":
        return "resume only after error remediation and a clean sampling run"
    if recommendation == "reduce" and strategic_weight >= 0.7:
        return "preserve minimum coverage because this source is strategically important"
    if recommendation == "reduce":
        return "shift budget gradually and monitor for evidence coverage loss"
    if error_rate > 0.2:
        return "hold budget while tracking whether error remediation improves reliability"
    return "maintain current budget and revisit after the next source quality review"


def _priority_score(recommendation: str, performance_score: float, error_rate: float, strategic_weight: float) -> float:
    if recommendation == "increase":
        score = performance_score + strategic_weight
    elif recommendation == "pause":
        score = error_rate + (1.0 - strategic_weight)
    elif recommendation == "reduce":
        score = error_rate + max(0.0, 0.8 - performance_score)
    else:
        score = strategic_weight + performance_score * 0.25
    return round(score, 4)


def _direction_order(recommendation: str) -> int:
    return {"increase": 0, "pause": 1, "reduce": 2, "hold": 3}.get(recommendation, 4)


def _bounded_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(max(0.0, min(1.0, number)), 4)


def _nonnegative_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, number)


def _clean(value: Any) -> str:
    return str(value or "").strip()
