"""Prompt cache efficiency export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.prompt_cache_efficiency_report.v1"
KIND = "max.prompt_cache_efficiency_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class PromptCacheEfficiencyInput(TypedDict, total=False):
    stage: str
    model: str
    request_count: int | float | str
    cache_hit_count: int | float | str
    input_tokens: int | float | str
    cached_tokens: int | float | str
    estimated_saved_tokens: int | float | str
    estimated_saved_cost: int | float | str


def build_prompt_cache_efficiency_report(
    records: Iterable[PromptCacheEfficiencyInput | dict[str, Any]],
    *,
    title: str = "Prompt Cache Efficiency Report",
    generated_at: str = DEFAULT_GENERATED_AT,
    low_efficiency_hit_rate_threshold: float = 0.8,
) -> dict[str, Any]:
    rows = _normalize_records(records)
    threshold = _threshold(low_efficiency_hit_rate_threshold)
    low_efficiency = [row for row in rows if row["hit_rate"] < threshold]
    low_efficiency.sort(key=lambda row: (row["hit_rate"], -row["request_count"], row["stage"].lower(), row["model"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Prompt Cache Efficiency Report",
        "summary": _summary(rows, threshold),
        "stage_efficiency": rows,
        "low_efficiency_stages": low_efficiency,
        "model_totals": _model_totals(rows),
    }


def render_prompt_cache_efficiency_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Prompt Cache Efficiency Report'}",
        "",
        "## Summary",
        "",
        f"- Stages: {summary.get('stage_count', 0)}",
        f"- Models: {summary.get('model_count', 0)}",
        f"- Requests: {summary.get('request_count', 0)}",
        f"- Cache hit rate: {summary.get('hit_rate', 0.0)}",
        f"- Cached token share: {summary.get('cached_token_share', 0.0)}",
        f"- Low-efficiency stages: {summary.get('low_efficiency_stage_count', 0)}",
        "",
        "## Low-Efficiency Stages",
        "",
    ]
    low_efficiency = report.get("low_efficiency_stages") or []
    if low_efficiency:
        for row in low_efficiency:
            lines.append(f"- {row['stage']} ({row['model']}): hit rate {row['hit_rate']}, cached token share {row['cached_token_share']}")
    else:
        lines.append("- No low-efficiency stages were found.")
    return "\n".join(lines).rstrip() + "\n"


def render_prompt_cache_efficiency_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(records: Iterable[PromptCacheEfficiencyInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for raw in records:
        request_count = _int(raw.get("request_count"))
        cache_hit_count = min(_int(raw.get("cache_hit_count")), request_count) if request_count else _int(raw.get("cache_hit_count"))
        input_tokens = _int(raw.get("input_tokens"))
        cached_tokens = min(_int(raw.get("cached_tokens")), input_tokens) if input_tokens else _int(raw.get("cached_tokens"))
        estimated_saved_tokens = _int(raw.get("estimated_saved_tokens"))
        rows.append(
            {
                "stage": _text(raw.get("stage")) or "unknown-stage",
                "model": _text(raw.get("model")) or "unknown-model",
                "request_count": request_count,
                "cache_hit_count": cache_hit_count,
                "hit_rate": _rate(cache_hit_count, request_count),
                "input_tokens": input_tokens,
                "cached_tokens": cached_tokens,
                "cached_token_share": _rate(cached_tokens, input_tokens),
                "estimated_saved_tokens": estimated_saved_tokens if estimated_saved_tokens else cached_tokens,
                "estimated_saved_cost": round(_float(raw.get("estimated_saved_cost")), 4),
            }
        )
    rows.sort(key=lambda row: (row["stage"].lower(), row["model"].lower()))
    return rows


def _summary(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    request_count = sum(row["request_count"] for row in rows)
    cache_hit_count = sum(row["cache_hit_count"] for row in rows)
    input_tokens = sum(row["input_tokens"] for row in rows)
    cached_tokens = sum(row["cached_tokens"] for row in rows)
    return {
        "stage_count": len(rows),
        "model_count": len({row["model"] for row in rows}),
        "request_count": request_count,
        "cache_hit_count": cache_hit_count,
        "hit_rate": _rate(cache_hit_count, request_count),
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "cached_token_share": _rate(cached_tokens, input_tokens),
        "estimated_saved_tokens": sum(row["estimated_saved_tokens"] for row in rows),
        "estimated_saved_cost": round(sum(row["estimated_saved_cost"] for row in rows), 4),
        "low_efficiency_hit_rate_threshold": threshold,
        "low_efficiency_stage_count": sum(1 for row in rows if row["hit_rate"] < threshold),
    }


def _model_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["model"]].append(row)

    totals = []
    for model, items in grouped.items():
        request_count = sum(item["request_count"] for item in items)
        cache_hit_count = sum(item["cache_hit_count"] for item in items)
        input_tokens = sum(item["input_tokens"] for item in items)
        cached_tokens = sum(item["cached_tokens"] for item in items)
        totals.append(
            {
                "model": model,
                "stage_count": len(items),
                "request_count": request_count,
                "cache_hit_count": cache_hit_count,
                "hit_rate": _rate(cache_hit_count, request_count),
                "input_tokens": input_tokens,
                "cached_tokens": cached_tokens,
                "cached_token_share": _rate(cached_tokens, input_tokens),
                "estimated_saved_tokens": sum(item["estimated_saved_tokens"] for item in items),
                "estimated_saved_cost": round(sum(item["estimated_saved_cost"] for item in items), 4),
            }
        )
    totals.sort(key=lambda row: row["model"].lower())
    return totals


def _threshold(value: Any) -> float:
    try:
        return round(min(max(float(value), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.8


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
