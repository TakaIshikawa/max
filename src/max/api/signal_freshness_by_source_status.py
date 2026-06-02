"""JSON API renderer for signal freshness by source status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import bool_or_default, float_or_zero, int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.signal_freshness_by_source_status.v1"
KIND = "max.api.signal_freshness_by_source_status"


def signal_freshness_by_source_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = parse_datetime(as_of or payload.get("as_of")) or datetime.now(timezone.utc)
    rows = [_row(row, now) for row in _items(payload)]
    rows.sort(key=lambda row: (_rank(row["status"]), row["source"]))
    critical = sum(1 for row in rows if row["status"] == "critical" and row["enabled"])
    warning = sum(1 for row in rows if row["status"] == "warning")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": "critical" if critical else "warning" if warning else "ok", "summary": {"source_count": len(rows), "critical_count": critical, "warning_count": warning, "empty_enabled_count": sum(1 for row in rows if row["enabled"] and row["signal_count"] == 0)}, "sources": rows, "metadata": source_metadata(payload, as_of=now.isoformat().replace("+00:00", "Z"), source_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("sources")) or list_of_maps(payload.get("items"))


def _row(row: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    enabled = bool_or_default(row.get("enabled"), default=True)
    signal_count = max(0, int_or_zero(row.get("signal_count")))
    sla = float_or_zero(row.get("freshness_sla_hours")) or 24.0
    observed = parse_datetime(row.get("newest_signal_at"))
    age_hours = round(max((now - observed).total_seconds() / 3600, 0), 2) if observed else None
    stale = age_hours is None or age_hours > sla
    status = "disabled" if not enabled else "critical" if signal_count == 0 or stale else "ok"
    return {"source": _bucket(row.get("source"), "unknown_source"), "newest_signal_at": observed.isoformat().replace("+00:00", "Z") if observed else None, "freshness_sla_hours": sla, "signal_count": signal_count, "enabled": enabled, "age_hours": age_hours, "status": status}


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2, "disabled": 3}.get(status, 4)


def _bucket(value: Any, default: str) -> str:
    text = " ".join(str(value).strip().split()) if value is not None else ""
    return (text or default).lower().replace(" ", "_")
