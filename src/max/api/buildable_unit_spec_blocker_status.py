"""JSON API renderer for buildable unit spec blocker status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import age_bucket, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.buildable_unit_spec_blocker_status.v1"
KIND = "max.api.buildable_unit_spec_blocker_status"


def buildable_unit_spec_blocker_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    rows = [_blocker(row, index, now) for index, row in enumerate(list_of_maps(payload.get("blockers") or payload.get("units") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (not row["approved"], row["blocker_type"], row["unit_id"]))
    approved_blocked = sum(1 for row in rows if row["approved"])
    status = "critical" if approved_blocked else ("degraded" if rows else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"health": status, "status": status, "blocked_unit_count": len(rows), "approved_blocked_count": approved_blocked, "unblockable_count": sum(1 for row in rows if row["unblockable"]), "manual_review_count": sum(1 for row in rows if not row["unblockable"])}, "blockers": rows, "blocker_types": _counts(rows, "blocker_type"), "recommendations": _counts(rows, "recommendation"), "profiles": _profiles(rows), "age_buckets": _counts(rows, "age_bucket"), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _blocker(item: Mapping[str, Any], index: int, now: datetime) -> dict[str, Any]:
    state = _text(item.get("approval_status") or item.get("status"))
    approved = bool(item.get("approved")) or state == "approved"
    recommendation = _text(item.get("recommendation") or ("unblock" if item.get("unblockable") else "manual_review"))
    return {"unit_id": _text(item.get("unit_id") or item.get("id") or f"unit-{index}"), "profile": _text(item.get("profile") or "default"), "blocker_type": _text(item.get("blocker_type") or item.get("type") or "unknown"), "recommendation": recommendation, "approved": approved, "unblockable": recommendation in {"unblock", "auto_unblock"} or bool(item.get("unblockable")), "age_bucket": age_bucket(item.get("created_at") or item.get("blocked_at"), now)}


def _counts(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts = Counter(row[field] for row in rows)
    return [{field: key, "count": value} for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _profiles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["profile"]].append(row)
    return sorted([{"profile": profile, "blocked_unit_count": len(items), "approved_blocked_count": sum(1 for item in items if item["approved"])} for profile, items in grouped.items()], key=lambda row: (-row["blocked_unit_count"], row["profile"]))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

