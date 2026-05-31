"""JSON API renderer for tact daemon connectivity status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import bool_or_default, float_or_zero, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.tact_daemon_connectivity_status.v1"
KIND = "max.api.tact_daemon_connectivity_status"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def tact_daemon_connectivity_status_to_json(payload: Mapping[str, Any], *, now: str | datetime | None = None, latency_warn_ms: float = 500.0, stale_success_hours: float = 24.0) -> str:
    as_of = parse_datetime(now) or parse_datetime(payload.get("now")) or datetime.now(timezone.utc)
    rows = _rows(payload, as_of, float_or_zero(payload.get("latency_warn_ms", latency_warn_ms)) or latency_warn_ms, float_or_zero(payload.get("stale_success_hours", stale_success_hours)) or stale_success_hours)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "targets": rows, "metadata": source_metadata(payload, target_count=len(rows), as_of=_dt(as_of))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], as_of: datetime, latency_warn_ms: float, stale_hours: float) -> list[dict[str, Any]]:
    source = payload.get("targets") if isinstance(payload.get("targets"), list) else []
    rows = [_row(item, index, as_of, latency_warn_ms, stale_hours) for index, item in enumerate(source, start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (SEVERITY_RANK[row["severity"]], row["target"]))


def _row(item: Mapping[str, Any], index: int, as_of: datetime, latency_warn_ms: float, stale_hours: float) -> dict[str, Any]:
    reachable = bool_or_default(item.get("reachable"), default=False)
    latency = float_or_zero(item.get("latency_ms"))
    last_success = parse_datetime(item.get("last_success_at"))
    stale = last_success is None or (as_of - last_success).total_seconds() / 3600 > stale_hours
    severity = "critical" if not reachable else ("warn" if stale or latency > latency_warn_ms else "ok")
    return {"target": _text(item.get("target") or item.get("name")) or f"target-{index}", "reachable": reachable, "latency_ms": round(latency, 2), "last_success_at": _dt(last_success), "last_error": item.get("last_error"), "severity": severity}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"target_count": len(rows), "unreachable_count": sum(1 for row in rows if not row["reachable"]), "severity": min((row["severity"] for row in rows), key=lambda value: SEVERITY_RANK[value], default="ok")}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _dt(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None
