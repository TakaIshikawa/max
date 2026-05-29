"""Source cost efficiency export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_cost_efficiency_report.v1"
KIND = "max.source_cost_efficiency_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_source_cost_efficiency_report(
    records: Iterable[dict[str, Any]],
    *,
    title: str = "Source Cost Efficiency Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in records:
        if isinstance(raw, dict):
            groups[_text(_first(raw, "source", "source_adapter", "adapter", "adapter_name")) or "unknown-source"].append(raw)

    rows = []
    for source, items in groups.items():
        cost_usd = sum(_number(_first(i, "cost_usd", "fetch_cost_usd", "spend_usd", "usd_cost", "cost")) for i in items)
        token_count = sum(_number(_first(i, "token_count", "tokens", "token_spend", "total_tokens")) for i in items)
        signal_count = sum(_number(_first(i, "signal_count", "signals", "total_signals", "emitted_signal_count")) for i in items)
        accepted_signal_count = sum(_number(_first(i, "accepted_signal_count", "accepted_signals", "accepted_count", "accepted")) for i in items)
        insight_count = sum(_number(_first(i, "insight_count", "insights", "accepted_insight_count")) for i in items)
        idea_count = sum(_number(_first(i, "idea_count", "ideas", "accepted_idea_count")) for i in items)

        cost_per_signal = _ratio(cost_usd, signal_count)
        cost_per_accepted_signal = _ratio(cost_usd, accepted_signal_count)
        insight_yield_rate = _ratio(insight_count, accepted_signal_count)
        idea_yield_rate = _ratio(idea_count, accepted_signal_count)

        rows.append(
            {
                "source": source,
                "cost_usd": round(cost_usd, 6),
                "token_count": int(token_count),
                "signal_count": int(signal_count),
                "accepted_signal_count": int(accepted_signal_count),
                "insight_count": int(insight_count),
                "idea_count": int(idea_count),
                "cost_per_signal": cost_per_signal,
                "cost_per_accepted_signal": cost_per_accepted_signal,
                "insight_yield_rate": insight_yield_rate,
                "idea_yield_rate": idea_yield_rate,
                "efficiency_status": _status(cost_per_accepted_signal, insight_yield_rate, idea_yield_rate, accepted_signal_count),
            }
        )

    rows.sort(key=lambda r: ({"inefficient": 0, "watch": 1, "efficient": 2, "no_yield": 3}[r["efficiency_status"]], r["source"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Source Cost Efficiency Report",
        "summary": {
            "source_count": len(groups),
            "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 6),
            "total_token_count": sum(r["token_count"] for r in rows),
            "inefficient_source_count": sum(1 for r in rows if r["efficiency_status"] == "inefficient"),
            "no_yield_source_count": sum(1 for r in rows if r["efficiency_status"] == "no_yield"),
        },
        "efficiency_rows": rows,
    }


def render_source_cost_efficiency_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_cost_efficiency_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source Cost Efficiency Report'}", "", "## Source Efficiency", ""]
    rows = report.get("efficiency_rows") or []
    lines.extend(
        [
            f"- {r['source']}: ${r['cost_per_accepted_signal']:.4f}/accepted signal, "
            f"{r['insight_yield_rate']:.2f} insight yield, {r['idea_yield_rate']:.2f} idea yield ({r['efficiency_status']})"
            for r in rows
        ]
        or ["- No source cost efficiency records available."]
    )
    return "\n".join(lines).rstrip() + "\n"


def _status(cost_per_accepted_signal: float, insight_yield_rate: float, idea_yield_rate: float, accepted_signal_count: float) -> str:
    if accepted_signal_count <= 0:
        return "no_yield"
    if cost_per_accepted_signal > 5.0 and insight_yield_rate == 0 and idea_yield_rate == 0:
        return "inefficient"
    if cost_per_accepted_signal > 2.0 or (insight_yield_rate + idea_yield_rate) < 0.25:
        return "watch"
    return "efficient"


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _number(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
