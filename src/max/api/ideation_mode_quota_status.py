"""JSON API renderer for ideation mode quota status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.ideation_mode_quota_status.v1"
KIND = "max.api.ideation_mode_quota_status"
STATUS_RANK = {"over_quota": 0, "exhausted": 1, "near_limit": 2, "available": 3}


def ideation_mode_quota_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    modes = _modes(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(modes), "modes": modes, "profile_mode_pressure": _profile_pressure(modes), "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, mode_count=len(modes))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _modes(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("modes") if isinstance(payload.get("modes"), list) else payload.get("items")
    if not isinstance(source, list):
        source = payload.get("quotas")
    rows = [_mode(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["usage_ratio"], row["mode"], row["profile"]))


def _mode(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    quota = max(0, int_or_zero(item.get("quota", item.get("limit", item.get("capacity")))))
    used = max(0, int_or_zero(item.get("used", item.get("usage", item.get("actual")))))
    remaining = max(quota - used, 0)
    ratio = round(used / quota, 4) if quota else (1.0 if used else 0.0)
    if used > quota and quota:
        status = "over_quota"
    elif remaining == 0 and quota:
        status = "exhausted"
    elif ratio >= 0.8:
        status = "near_limit"
    else:
        status = "available"
    return {"mode": _bucket(item.get("mode") or item.get("name"), f"mode_{index}"), "profile": _bucket(item.get("profile"), "default"), "quota": quota, "used": used, "remaining": remaining, "usage_ratio": round(min(ratio, 1.0), 4), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    status = "over_quota" if counts["over_quota"] else ("exhausted" if counts["exhausted"] else ("near_limit" if counts["near_limit"] else "available"))
    return {"status": status, "mode_count": len(rows), "over_quota_count": counts["over_quota"], "exhausted_count": counts["exhausted"], "near_limit_count": counts["near_limit"]}


def _profile_pressure(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles = sorted({row["profile"] for row in rows})
    return [{"profile": profile, "mode_count": sum(1 for row in rows if row["profile"] == profile), "max_usage_ratio": max((row["usage_ratio"] for row in rows if row["profile"] == profile), default=0.0)} for profile in profiles]


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
