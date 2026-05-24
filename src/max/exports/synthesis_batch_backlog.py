"""Synthesis batch backlog export report."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, int_or_zero, parse_datetime

SCHEMA_VERSION = "max.exports.synthesis_batch_backlog.v1"
KIND = "max.exports.synthesis_batch_backlog"
AGE_BUCKETS = ("0_1h", "2_6h", "7_24h", "over_24h", "unknown")
STATUS_RANK = {"stalled": 0, "backlogged": 1, "normal": 2}


def generate_synthesis_batch_backlog_report(records: Iterable[Mapping[str, Any]] | Mapping[str, Any], *, as_of: str | datetime | None = None) -> dict[str, Any]:
    effective_as_of = parse_datetime(as_of) or parse_datetime(records.get("as_of") if isinstance(records, Mapping) else None)
    batches = _batches(records, effective_as_of)
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(batches), "batches": batches, "profile_totals": _profile_totals(batches), "age_buckets": _age_buckets(batches), "oldest_queued_batch": _oldest(batches), "metadata": {"as_of": datetime_to_string(effective_as_of), "batch_count": len(batches)}}


def render_synthesis_batch_backlog_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def _batches(records: Iterable[Mapping[str, Any]] | Mapping[str, Any], as_of: datetime | None) -> list[dict[str, Any]]:
    source = records.get("batches") if isinstance(records, Mapping) else records
    rows = [_batch(item, index, as_of) for index, item in enumerate(source if isinstance(source, list) else list(source), start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["age_hours"], row["profile"], row["batch_id"]))


def _batch(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    raw_status = _text(item.get("status")) or "queued"
    queued_at = item.get("queued_at") or item.get("created_at")
    age_hours = _age_hours(queued_at, as_of) if raw_status == "queued" else 0
    status = "stalled" if raw_status == "failed" or age_hours >= 24 else ("backlogged" if raw_status == "queued" and age_hours >= 6 else "normal")
    return {"batch_id": _text(item.get("batch_id") or item.get("id")) or f"batch-{index}", "profile": _text(item.get("profile")) or "unknown-profile", "raw_status": raw_status, "age_bucket": _age_bucket(age_hours, raw_status), "age_hours": age_hours, "item_count": max(0, int_or_zero(item.get("item_count", item.get("items")))), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    raw = Counter(row["raw_status"] for row in rows)
    status = Counter(row["status"] for row in rows)
    return {"batch_count": len(rows), "queued_count": raw["queued"], "running_count": raw["running"], "failed_count": raw["failed"], "completed_count": raw["completed"], "failed_batch_total": raw["failed"], "status": "stalled" if status["stalled"] else ("backlogged" if status["backlogged"] else "normal")}


def _profile_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["profile"]].append(row)
    output = []
    for profile, items in grouped.items():
        raw = Counter(item["raw_status"] for item in items)
        status = Counter(item["status"] for item in items)
        output.append({"profile": profile, "batch_count": len(items), "queued_count": raw["queued"], "running_count": raw["running"], "failed_count": raw["failed"], "completed_count": raw["completed"], "status": "stalled" if status["stalled"] else ("backlogged" if status["backlogged"] else "normal")})
    return sorted(output, key=lambda row: (STATUS_RANK[row["status"]], row["profile"]))


def _age_buckets(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(row["age_bucket"] for row in rows)
    return {bucket: counts[bucket] for bucket in AGE_BUCKETS}


def _oldest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    queued = [row for row in rows if row["raw_status"] == "queued"]
    return max(queued, key=lambda row: row["age_hours"]) if queued else None


def _age_hours(value: Any, as_of: datetime | None) -> int:
    queued_at = parse_datetime(value)
    if queued_at is None or as_of is None:
        return 0
    return max(0, int((as_of - queued_at).total_seconds() // 3600))


def _age_bucket(age: int, status: str) -> str:
    if status != "queued":
        return "unknown"
    if age <= 1:
        return "0_1h"
    if age <= 6:
        return "2_6h"
    if age <= 24:
        return "7_24h"
    return "over_24h"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""

