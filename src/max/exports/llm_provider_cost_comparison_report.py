"""LLM provider cost comparison export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.llm_provider_cost_comparison_report.v1"
KIND = "max.llm_provider_cost_comparison_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_llm_provider_cost_comparison_report(
    records: Iterable[dict[str, Any]],
    *,
    title: str = "LLM Provider Cost Comparison Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = []
    for raw in records:
        tokens = _int(raw.get("token_count") or raw.get("tokens"))
        requests = _int(raw.get("request_count") or raw.get("requests"))
        cost = _float(raw.get("cost_usd") or raw.get("cost"))
        baseline = _float(raw.get("baseline_cost_usd") or raw.get("baseline_cost"))
        rows.append(
            {
                "provider": _text(raw.get("provider")) or "unknown-provider",
                "model": _text(raw.get("model")) or "unknown-model",
                "token_count": tokens,
                "request_count": requests,
                "cost_usd": round(cost, 4),
                "average_cost_per_request": _rate(cost, requests),
                "cost_per_1k_tokens": round((cost / tokens) * 1000, 6) if tokens else 0.0,
                "baseline_cost_usd": round(baseline, 4),
                "baseline_variance_usd": round(cost - baseline, 4),
                "baseline_variance_rate": _rate(cost - baseline, baseline),
            }
        )
    rows.sort(key=lambda row: (-row["cost_usd"], row["provider"].lower(), row["model"].lower()))
    provider_totals = _provider_totals(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "LLM Provider Cost Comparison Report",
        "summary": {
            "provider_count": len(provider_totals),
            "model_count": len(rows),
            "total_cost_usd": round(sum(row["cost_usd"] for row in rows), 4),
            "token_count": sum(row["token_count"] for row in rows),
            "request_count": sum(row["request_count"] for row in rows),
            "highest_cost_provider": provider_totals[0]["provider"] if provider_totals else None,
        },
        "provider_model_costs": rows,
        "provider_totals": provider_totals,
    }


def render_llm_provider_cost_comparison_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_llm_provider_cost_comparison_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'LLM Provider Cost Comparison Report'}",
        "",
        "## Summary",
        "",
        f"- Total cost USD: {summary.get('total_cost_usd', 0.0)}",
        f"- Highest cost provider: {summary.get('highest_cost_provider') or 'n/a'}",
        f"- Requests: {summary.get('request_count', 0)}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _provider_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    providers = sorted({row["provider"] for row in rows}, key=str.lower)
    totals = [
        {
            "provider": provider,
            "cost_usd": round(sum(row["cost_usd"] for row in rows if row["provider"] == provider), 4),
            "token_count": sum(row["token_count"] for row in rows if row["provider"] == provider),
            "request_count": sum(row["request_count"] for row in rows if row["provider"] == provider),
        }
        for provider in providers
    ]
    totals.sort(key=lambda row: (-row["cost_usd"], row["provider"].lower()))
    return totals


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


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
