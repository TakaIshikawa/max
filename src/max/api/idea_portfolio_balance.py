"""JSON API renderer for idea portfolio balance."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.idea_portfolio_balance.v1"
KIND = "max.api.idea_portfolio_balance"
BUCKETS = ("domain", "stage", "recommendation", "risk_band")


def idea_portfolio_balance_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    ideas = _ideas(payload)
    threshold = _threshold(payload.get("dominance_threshold", payload.get("threshold", 0.6)))
    bucket_summaries = {bucket: _bucket_summary(ideas, bucket) for bucket in BUCKETS}
    warnings = _warnings(bucket_summaries, threshold)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(ideas, warnings, threshold),
        "ideas": ideas,
        "bucket_summaries": bucket_summaries,
        "imbalance_warnings": warnings,
        "recommended_rebalance_actions": _actions(warnings),
        "metadata": _metadata(payload, ideas, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _ideas(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("ideas") if isinstance(payload.get("ideas"), list) else payload.get("items")
    rows = [_idea(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (row["domain"], row["stage"], row["recommendation"], row["risk_band"], row["idea_id"]))
    return rows


def _idea(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "idea_id": _text(item.get("idea_id") or item.get("id")) or f"idea-{index}",
        "title": _text(item.get("title") or item.get("name")),
        "domain": _bucket(item.get("domain") or item.get("market") or item.get("category"), "unknown-domain"),
        "stage": _bucket(item.get("stage") or item.get("status"), "unknown-stage"),
        "recommendation": _bucket(item.get("recommendation") or item.get("verdict"), "unknown-recommendation"),
        "risk_band": _bucket(item.get("risk_band") or item.get("risk"), "unknown-risk"),
    }


def _bucket_summary(ideas: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    total = len(ideas)
    counts = Counter(row[field] for row in ideas)
    rows = [{"bucket": bucket, "count": count, "percentage": round(count / total, 4) if total else 0.0} for bucket, count in counts.items()]
    rows.sort(key=lambda row: (-row["count"], row["bucket"]))
    return rows


def _warnings(bucket_summaries: dict[str, list[dict[str, Any]]], threshold: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension, buckets in bucket_summaries.items():
        for bucket in buckets:
            if bucket["percentage"] > threshold:
                rows.append(
                    {
                        "dimension": dimension,
                        "bucket": bucket["bucket"],
                        "count": bucket["count"],
                        "percentage": bucket["percentage"],
                        "threshold": threshold,
                        "warning": f"{dimension} bucket {bucket['bucket']} exceeds portfolio dominance threshold",
                    }
                )
    rows.sort(key=lambda row: (-row["percentage"], row["dimension"], row["bucket"]))
    return rows


def _actions(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"rebalance-{row['dimension']}-{row['bucket']}",
            "dimension": row["dimension"],
            "bucket": row["bucket"],
            "action": f"Add or promote ideas outside {row['dimension']}={row['bucket']}",
        }
        for row in warnings
    ]


def _summary(ideas: list[dict[str, Any]], warnings: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    return {
        "idea_count": len(ideas),
        "dominance_threshold": threshold,
        "warning_count": len(warnings),
        "balanced": not warnings,
    }


def _metadata(payload: Mapping[str, Any], ideas: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "idea_count": len(ideas)}


def _threshold(value: Any) -> float:
    try:
        return round(min(max(float(value), 0.01), 1.0), 4)
    except (TypeError, ValueError):
        return 0.6


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
