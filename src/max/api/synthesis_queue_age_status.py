"""JSON API renderer for synthesis queue age status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.synthesis_queue_age_status.v1"
KIND = "max.api.synthesis_queue_age_status"


def synthesis_queue_age_status_to_json(
    payload: Mapping[str, Any],
    *,
    now: str | datetime | None = None,
    warning_age_seconds: int | None = None,
    critical_age_seconds: int | None = None,
) -> str:
    as_of = parse_datetime(now) or datetime.now(timezone.utc)
    warn = _int(warning_age_seconds if warning_age_seconds is not None else payload.get("warning_age_seconds"), 3600)
    critical = _int(critical_age_seconds if critical_age_seconds is not None else payload.get("critical_age_seconds"), 7200)
    rows = _rows(payload, as_of, warn, critical)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(rows, warn, critical),
        "rows": rows,
        "metadata": source_metadata(payload, as_of=as_of.isoformat().replace("+00:00", "Z"), queue_count=len(rows)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], as_of: datetime, warn: int, critical: int) -> list[dict[str, Any]]:
    source = payload.get("batches") if isinstance(payload.get("batches"), list) else payload.get("queue")
    items = [item for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    grouped: dict[tuple[str, str], dict[str, int]] = {}
    for item in items:
        key = (_text(item.get("profile") or item.get("profile_id"), "unspecified"), _text(item.get("source") or item.get("source_name"), "unspecified"))
        queued_at = parse_datetime(item.get("queued_at") or item.get("created_at") or item.get("submitted_at"))
        age = max(0, int((as_of - queued_at).total_seconds())) if queued_at else 0
        bucket = grouped.setdefault(key, {"queued_count": 0, "oldest_queued_age_seconds": 0, "stale_batch_count": 0})
        bucket["queued_count"] += 1
        bucket["oldest_queued_age_seconds"] = max(bucket["oldest_queued_age_seconds"], age)
        if age >= warn:
            bucket["stale_batch_count"] += 1
    rows = [_row(profile, source_name, counts, warn, critical) for (profile, source_name), counts in grouped.items()]
    return sorted(rows, key=lambda row: (row["severity_rank"], -row["oldest_queued_age_seconds"], row["profile"], row["source"]))


def _row(profile: str, source_name: str, counts: Mapping[str, int], warn: int, critical: int) -> dict[str, Any]:
    oldest = counts["oldest_queued_age_seconds"]
    severity = "critical" if oldest >= critical else "warn" if oldest >= warn else "healthy"
    return {**counts, "profile": profile, "source": source_name, "severity": severity, "severity_rank": {"critical": 0, "warn": 1, "healthy": 2}[severity]}


def _summary(rows: list[dict[str, Any]], warn: int, critical: int) -> dict[str, Any]:
    status = "critical" if any(row["severity"] == "critical" for row in rows) else "warn" if any(row["severity"] == "warn" for row in rows) else "healthy"
    return {"status": status, "group_count": len(rows), "total_queued_count": sum(row["queued_count"] for row in rows), "oldest_queued_age_seconds": max([row["oldest_queued_age_seconds"] for row in rows] or [0]), "stale_batch_count": sum(row["stale_batch_count"] for row in rows), "warning_age_seconds": warn, "critical_age_seconds": critical}


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any, default: str) -> str:
    return " ".join(str(value).strip().split()) if value not in (None, "") else default
