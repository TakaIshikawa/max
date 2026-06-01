"""JSON API renderer for feedback outcome freshness status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import float_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.feedback_outcome_freshness_status.v1"
KIND = "max.api.feedback_outcome_freshness_status"


def feedback_outcome_freshness_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    threshold = float_or_zero(payload.get("freshness_threshold_hours") or payload.get("threshold_hours") or 72)
    segments = [_segment(row, i, as_of, threshold) for i, row in enumerate(list_of_maps(payload.get("segments") or payload.get("outcomes") or payload.get("rows")), start=1)]
    stale = [row for row in segments if row["stale"]]
    missing = [row for row in segments if row["missing_outcome"]]
    status = "critical" if missing else ("warning" if stale else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "overall_status": status, "total_segments": len(segments), "stale_segment_count": len(stale), "missing_outcome_count": len(missing), "stale_segments": sorted(stale, key=lambda row: (row["profile"].casefold(), row["reviewer"].casefold())), "missing_outcome_blockers": sorted(missing, key=lambda row: (row["profile"].casefold(), row["reviewer"].casefold())), "segments": sorted(segments, key=lambda row: (row["profile"].casefold(), row["reviewer"].casefold())), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _segment(item: Mapping[str, Any], index: int, as_of: datetime, threshold: float) -> dict[str, Any]:
    newest = parse_datetime(item.get("newest_outcome_at") or item.get("last_outcome_at") or item.get("outcome_at"))
    age_hours = round((as_of - newest).total_seconds() / 3600, 2) if newest else None
    missing = newest is None or _text(item.get("outcome_status")).casefold() in {"missing", "none", "blocked"}
    stale = missing or (age_hours is not None and age_hours > threshold)
    status = "critical" if missing else ("warning" if stale else "healthy")
    return {"segment": _text(item.get("segment") or item.get("id")) or f"segment-{index}", "profile": _text(item.get("profile")) or "default", "reviewer": _text(item.get("reviewer")) or "unassigned", "newest_outcome_at": item.get("newest_outcome_at") or item.get("last_outcome_at") or item.get("outcome_at"), "outcome_age_hours": age_hours, "freshness_threshold_hours": threshold, "missing_outcome": missing, "stale": stale, "status": status, "recommended_action": "capture missing feedback outcome" if missing else ("refresh feedback outcome" if stale else "continue monitoring")}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
