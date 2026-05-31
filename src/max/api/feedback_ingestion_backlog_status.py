"""JSON API renderer for feedback ingestion backlog status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.feedback_ingestion_backlog_status.v1"
KIND = "max.api.feedback_ingestion_backlog_status"
KNOWN_LABELS = {"approval", "rejection", "outcome"}
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def feedback_ingestion_backlog_status_to_json(payload: Mapping[str, Any], *, now: str | datetime | None = None) -> str:
    as_of = parse_datetime(now) or parse_datetime(payload.get("now")) or datetime.now(timezone.utc)
    rows = _rows(payload, as_of)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(rows),
        "label_mix": _label_mix(rows),
        "events": rows,
        "metadata": source_metadata(payload, event_count=len(rows), as_of=_dt(as_of)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], as_of: datetime) -> list[dict[str, Any]]:
    source = payload.get("events") if isinstance(payload.get("events"), list) else payload.get("backlog")
    rows = [_row(item, index, as_of) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (-row["age_hours"], row["label_bucket"], row["event_id"]))


def _row(item: Mapping[str, Any], index: int, as_of: datetime) -> dict[str, Any]:
    label = _bucket(item.get("label") or item.get("event_label") or item.get("type"), "unknown")
    created_at = parse_datetime(item.get("created_at") or item.get("queued_at"))
    age = round(max((as_of - created_at).total_seconds() / 3600, 0.0), 2) if created_at else 0.0
    return {
        "event_id": _text(item.get("event_id") or item.get("id")) or f"event-{index}",
        "label": label,
        "label_bucket": label if label in KNOWN_LABELS else "unknown",
        "queued_at": _dt(created_at),
        "age_hours": age,
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    oldest = max((row["age_hours"] for row in rows), default=0.0)
    severity = "critical" if count >= 100 or oldest >= 24 else ("warn" if count >= 25 or oldest >= 6 else "ok")
    return {"backlog_count": count, "oldest_age_hours": oldest, "severity": severity}


def _label_mix(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(row["label_bucket"] for row in rows)
    return {label: counts[label] for label in sorted(KNOWN_LABELS | {"unknown"}) if counts[label]}


def _bucket(value: Any, default: str) -> str:
    text = _text(value).lower().replace(" ", "_")
    return text or default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _dt(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None
