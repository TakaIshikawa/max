"""JSON API renderer for insight staleness distribution status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.insight_staleness_distribution_status.v1"
KIND = "max.api.insight_staleness_distribution_status"
BUCKET_RANK = {"expired": 0, "stale": 1, "warming": 2, "fresh": 3}


def insight_staleness_distribution_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    thresholds = {"fresh": float_or_zero(payload.get("fresh_days", 2)), "warming": float_or_zero(payload.get("warming_days", 7)), "stale": float_or_zero(payload.get("stale_days", 30))}
    rows = [_row(item, index, as_of, thresholds) for index, item in enumerate(list_of_maps(payload.get("insights") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (BUCKET_RANK[row["bucket"]], -row["age_days"], row["insight_id"]))
    bucket_counts = {bucket: sum(1 for row in rows if row["bucket"] == bucket) for bucket in ("fresh", "warming", "stale", "expired")}
    expired = [row for row in rows if row["bucket"] == "expired"]
    stale_count = bucket_counts["stale"] + bucket_counts["expired"]
    status = "no_data" if not rows else ("critical" if expired else ("warning" if stale_count else "healthy"))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "insight_count": len(rows), "stale_count": stale_count, "expired_count": len(expired), "bucket_counts": bucket_counts}, "insights": rows, "groups": _groups(rows), "expired_insights": expired, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, as_of: datetime, thresholds: Mapping[str, float]) -> dict[str, Any]:
    age = float_or_zero(item.get("age_days"))
    if "age_days" not in item:
        generated = parse_datetime(item.get("generated_at") or item.get("last_seen_at"))
        age = max((as_of - generated).total_seconds() / 86400, 0.0) if generated else 0.0
    bucket = "fresh" if age <= thresholds["fresh"] else ("warming" if age <= thresholds["warming"] else ("stale" if age <= thresholds["stale"] else "expired"))
    return {"insight_id": str(item.get("insight_id") or item.get("id") or f"insight-{index}"), "profile": str(item.get("profile") or item.get("profile_id") or "unknown_profile"), "source": str(item.get("source") or "unknown_source"), "age_days": round(age, 2), "bucket": bucket, "generated_at": item.get("generated_at"), "last_seen_at": item.get("last_seen_at")}


def _groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({(row["profile"], row["source"]) for row in rows})
    return [{"profile": profile, "source": source, "insight_count": sum(1 for row in rows if row["profile"] == profile and row["source"] == source)} for profile, source in keys]
