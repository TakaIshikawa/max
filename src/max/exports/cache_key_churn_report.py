"""Cache key churn export report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.cache_key_churn_report.v1"
KIND = "max.cache_key_churn_report"
DEFAULT_GENERATED_AT = "2026-05-29T00:00:00+00:00"


def generate_cache_key_churn_report(
    records: Iterable[dict[str, Any]],
    *,
    churn_threshold: float = 0.3,
    title: str = "Cache Key Churn Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    threshold = _threshold(churn_threshold)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in records:
        if isinstance(raw, dict):
            groups[_text(raw.get("namespace")) or _text(raw.get("cache_namespace")) or "unknown-namespace"].append(raw)

    rows = []
    for namespace, items in groups.items():
        keys = [_text(item.get("key")) or _text(item.get("cache_key")) or "unknown-key" for item in items]
        unique_key_count = len(set(keys))
        total_events = len(items)
        churn_ratio = _rate(unique_key_count, total_events)
        rows.append(
            {
                "namespace": namespace,
                "unique_key_count": unique_key_count,
                "total_events": total_events,
                "churn_ratio": churn_ratio,
                "churn_threshold": threshold,
                "action_required": churn_ratio > threshold,
            }
        )
    rows.sort(key=lambda row: (-row["churn_ratio"], row["namespace"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Cache Key Churn Report",
        "summary": {
            "namespace_count": len(rows),
            "total_events": sum(row["total_events"] for row in rows),
            "unique_key_count": sum(row["unique_key_count"] for row in rows),
            "churn_threshold": threshold,
            "action_required_count": sum(1 for row in rows if row["action_required"]),
        },
        "namespace_rows": rows,
    }


def render_cache_key_churn_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _threshold(value: Any) -> float:
    try:
        return round(min(max(float(value), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.3


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
