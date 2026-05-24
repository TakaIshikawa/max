"""JSON API renderer for embedding similarity threshold status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.embedding_similarity_threshold_status.v1"
KIND = "max.api.embedding_similarity_threshold_status"
STATUS_RANK = {"drifting": 0, "loose": 1, "strict": 2, "balanced": 3}


def embedding_similarity_threshold_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    profiles = _profiles(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(profiles),
        "profiles": profiles,
        "status_totals": _status_totals(profiles),
        "drifting_profiles": [row for row in profiles if row["status"] == "drifting"],
        "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, profile_count=len(profiles)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _profiles(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("profiles") if isinstance(payload.get("profiles"), list) else payload.get("thresholds")
    rows = [_profile(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["index"]))


def _profile(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    threshold = _ratio(item.get("threshold", item.get("similarity_threshold", 0.85)))
    match_rate = _ratio(item.get("observed_match_rate", item.get("match_rate")))
    false_positive = _ratio(item.get("false_positive_rate", item.get("false_positive_hint")))
    drift = _ratio(item.get("drift_score", item.get("drift")))
    if drift >= 0.25 or false_positive >= 0.2:
        status = "drifting"
    elif threshold >= 0.9:
        status = "strict"
    elif threshold < 0.75 or match_rate >= 0.7:
        status = "loose"
    else:
        status = "balanced"
    return {
        "profile": _text(item.get("profile")) or f"profile-{index}",
        "index": _text(item.get("index") or item.get("index_id")) or "default",
        "threshold": threshold,
        "observed_match_rate": match_rate,
        "false_positive_rate": false_positive,
        "drift_score": drift,
        "sample_count": max(0, int_or_zero(item.get("sample_count", item.get("samples")))),
        "status": status,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"profile_count": len(rows), "strict_count": counts["strict"], "balanced_count": counts["balanced"], "loose_count": counts["loose"], "drifting_count": counts["drifting"]}


def _status_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["status"] for row in rows)
    return [{"status": status, "profile_count": counts[status]} for status in ("drifting", "loose", "strict", "balanced")]


def _ratio(value: Any) -> float:
    return round(min(max(float_or_zero(value), 0.0), 1.0), 4)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

