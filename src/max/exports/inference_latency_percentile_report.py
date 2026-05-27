"""Inference latency percentile export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.inference_latency_percentile_report.v1"
KIND = "max.inference_latency_percentile_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_inference_latency_percentile_report(
    records: Iterable[dict[str, Any]],
    *,
    title: str = "Inference Latency Percentile Report",
    generated_at: str = DEFAULT_GENERATED_AT,
    sla_ms: int | float = 1000,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for raw in records:
        latency = _float(raw.get("latency_ms") or raw.get("duration_ms"))
        if latency <= 0:
            continue
        grouped[(_text(raw.get("model")) or "unknown-model", _text(raw.get("stage")) or "unknown-stage", _text(raw.get("profile")) or "unknown-profile")].append(latency)
    threshold = max(0.0, float(sla_ms))
    rows = []
    for (model, stage, profile), values in grouped.items():
        values = sorted(values)
        rows.append(
            {
                "model": model,
                "stage": stage,
                "profile": profile,
                "sample_count": len(values),
                "p50_ms": _percentile(values, 50),
                "p90_ms": _percentile(values, 90),
                "p95_ms": _percentile(values, 95),
                "max_latency_ms": round(max(values), 2),
                "sla_ms": round(threshold, 2),
                "sla_breached": max(values) > threshold if threshold else False,
            }
        )
    rows.sort(key=lambda row: (row["model"].lower(), row["stage"].lower(), row["profile"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Inference Latency Percentile Report",
        "summary": {
            "sample_count": sum(row["sample_count"] for row in rows),
            "group_count": len(rows),
            "max_latency_ms": max((row["max_latency_ms"] for row in rows), default=0),
            "breached_group_count": sum(1 for row in rows if row["sla_breached"]),
        },
        "latency_groups": rows,
    }


def render_inference_latency_percentile_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_inference_latency_percentile_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Inference Latency Percentile Report'}", "", "## Summary", "", f"- Samples: {summary.get('sample_count', 0)}", f"- Max latency ms: {summary.get('max_latency_ms', 0)}", f"- Breached groups: {summary.get('breached_group_count', 0)}"]).rstrip() + "\n"


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    index = round((len(values) - 1) * percentile / 100)
    return round(values[index], 2)


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
