"""JSON API renderer for synthesis batch backlog status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.synthesis_batch_backlog_status.v1"
KIND = "max.api.synthesis_batch_backlog_status"
STATUS_RANK = {"stalled": 0, "backlogged": 1, "normal": 2}


def synthesis_batch_backlog_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    effective_as_of = parse_datetime(as_of) or parse_datetime(payload.get("as_of"))
    batches = _batches(payload, effective_as_of)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(batches),
        "batches": batches,
        "profile_totals": _profile_totals(batches),
        "stalled_batches": [row for row in batches if row["status"] == "failed" or row["age_hours"] >= 24],
        "metadata": source_metadata(payload, as_of=datetime_to_string(effective_as_of), batch_count=len(batches)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _batches(payload: Mapping[str, Any], as_of: datetime | None) -> list[dict[str, Any]]:
    source = payload.get("batches") if isinstance(payload.get("batches"), list) else payload.get("synthesis_batches")
    rows = [_batch(item, index, as_of) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["backlog_status"]], -row["age_hours"], row["profile"], row["batch_id"]))


def _batch(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    queued_at = item.get("queued_at") or item.get("created_at")
    status = _text(item.get("status")) or "queued"
    age_hours = _age_hours(queued_at, as_of) if status == "queued" else 0
    backlog_status = "stalled" if status == "failed" or age_hours >= 24 else ("backlogged" if status == "queued" and age_hours >= 6 else "normal")
    return {"batch_id": _text(item.get("batch_id") or item.get("id")) or f"batch-{index}", "profile": _text(item.get("profile")) or "unknown-profile", "status": status, "queued_at": queued_at, "age_hours": age_hours, "item_count": max(0, int_or_zero(item.get("item_count", item.get("items")))), "backlog_status": backlog_status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    backlog = Counter(row["backlog_status"] for row in rows)
    queued_ages = [row["age_hours"] for row in rows if row["status"] == "queued"]
    return {"batch_count": len(rows), "queued_count": counts["queued"], "running_count": counts["running"], "failed_count": counts["failed"], "completed_count": counts["completed"], "oldest_queued_age_hours": max(queued_ages) if queued_ages else 0, "status": "stalled" if backlog["stalled"] else ("backlogged" if backlog["backlogged"] else "normal")}


def _profile_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["profile"]].append(row)
    output = []
    for profile, items in grouped.items():
        counts = Counter(item["status"] for item in items)
        backlog = Counter(item["backlog_status"] for item in items)
        output.append({"profile": profile, "batch_count": len(items), "queued_count": counts["queued"], "running_count": counts["running"], "failed_count": counts["failed"], "completed_count": counts["completed"], "status": "stalled" if backlog["stalled"] else ("backlogged" if backlog["backlogged"] else "normal")})
    return sorted(output, key=lambda row: (STATUS_RANK[row["status"]], row["profile"]))


def _age_hours(value: Any, as_of: datetime | None) -> int:
    queued_at = parse_datetime(value)
    if queued_at is None or as_of is None:
        return 0
    return max(0, int((as_of - queued_at).total_seconds() // 3600))


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

