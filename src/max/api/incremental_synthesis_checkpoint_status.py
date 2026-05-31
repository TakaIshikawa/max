"""JSON API renderer for incremental synthesis checkpoint status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import float_or_zero, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.incremental_synthesis_checkpoint_status.v1"
KIND = "max.api.incremental_synthesis_checkpoint_status"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def incremental_synthesis_checkpoint_status_to_json(payload: Mapping[str, Any], *, now: str | datetime | None = None, stale_hours: float = 24.0, missing_is_critical: bool = True) -> str:
    as_of = parse_datetime(now) or parse_datetime(payload.get("now")) or datetime.now(timezone.utc)
    warn_after = float_or_zero(payload.get("stale_hours", stale_hours)) or stale_hours
    rows = _rows(payload, as_of, warn_after, missing_is_critical)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "checkpoints": rows, "metadata": source_metadata(payload, checkpoint_count=len(rows), as_of=_dt(as_of))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], as_of: datetime, stale_hours: float, missing_is_critical: bool) -> list[dict[str, Any]]:
    source = payload.get("checkpoints") if isinstance(payload.get("checkpoints"), list) else []
    rows = [_row(item, index, as_of, stale_hours, missing_is_critical) for index, item in enumerate(source, start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (SEVERITY_RANK[row["severity"]], row["source"], row["profile"]))


def _row(item: Mapping[str, Any], index: int, as_of: datetime, stale_hours: float, missing_is_critical: bool) -> dict[str, Any]:
    last = parse_datetime(item.get("last_processed_at") or item.get("checkpoint_at"))
    age = round(max((as_of - last).total_seconds() / 3600, 0.0), 2) if last else None
    severity = "critical" if last is None and missing_is_critical else ("critical" if age is not None and age >= stale_hours * 2 else ("warn" if age is None or age > stale_hours else "ok"))
    return {"source": _text(item.get("source")) or f"source-{index}", "profile": _text(item.get("profile")) or "default", "last_processed_at": _dt(last), "checkpoint_age_hours": age, "severity": severity}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"checkpoint_count": len(rows), "missing_count": sum(1 for row in rows if row["last_processed_at"] is None), "stale_count": sum(1 for row in rows if row["severity"] != "ok"), "severity": min((row["severity"] for row in rows), key=lambda value: SEVERITY_RANK[value], default="ok")}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _dt(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None
