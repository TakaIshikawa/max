"""JSON API renderer for profile signal quota status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.profile_signal_quota_status.v1"
KIND = "max.api.profile_signal_quota_status"


def profile_signal_quota_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "exhausted_profiles": [row for row in rows if row["exhausted"]], "metadata": source_metadata(payload, profile_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("profiles") if isinstance(payload.get("profiles"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["exhausted"], -row["usage_ratio"], row["profile"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    quota = max(0, int_or_zero(item.get("quota")))
    consumed = max(0, int_or_zero(item.get("consumed")))
    remaining = max(0, quota - consumed)
    ratio = round(consumed / quota, 4) if quota else (1.0 if consumed else 0.0)
    exhausted = bool(quota and consumed >= quota)
    return {"profile": _bucket(item.get("profile"), "default"), "quota": quota, "consumed": consumed, "remaining": remaining, "usage_ratio": ratio, "exhausted": exhausted, "rebalance_hint": _text(item.get("rebalance_hint")) or ("rebalance or raise quota" if exhausted else "none")}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "quota_exhausted" if any(row["exhausted"] for row in rows) else "available", "profile_count": len(rows), "total_quota": sum(row["quota"] for row in rows), "total_consumed": sum(row["consumed"] for row in rows), "exhausted_count": sum(1 for row in rows if row["exhausted"]), "highest_usage_ratio": max((row["usage_ratio"] for row in rows), default=0.0)}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
