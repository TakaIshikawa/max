"""JSON API renderer for publisher destination health status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.publisher_destination_health_status.v1"
KIND = "max.api.publisher_destination_health_status"
STATUS_RANK = {"unavailable": 0, "degraded": 1, "healthy": 2}


def publisher_destination_health_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "metadata": source_metadata(payload, destination_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("destinations") if isinstance(payload.get("destinations"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["destination"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    success = max(0, int_or_zero(item.get("success_count")))
    failure = max(0, int_or_zero(item.get("failure_count")))
    total = success + failure
    rate = round(failure / total, 4) if total else 0.0
    slo = max(0.0, float_or_zero(item.get("failure_rate_slo")))
    unavailable = bool(failure and not _text(item.get("last_success_at")))
    degraded = rate > slo if slo else bool(failure)
    status = "unavailable" if unavailable else ("degraded" if degraded else "healthy")
    return {"destination": _bucket(item.get("destination"), "unknown"), "publisher_type": _bucket(item.get("publisher_type"), "unknown"), "success_count": success, "failure_count": failure, "last_success_at": _text(item.get("last_success_at")) or None, "last_failure_at": _text(item.get("last_failure_at")) or None, "failure_rate_slo": round(slo, 4), "failure_rate": rate, "degraded": degraded, "unavailable": unavailable, "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "unavailable" if any(row["unavailable"] for row in rows) else ("degraded" if any(row["degraded"] for row in rows) else "healthy"), "destination_count": len(rows), "degraded_destinations": sum(1 for row in rows if row["degraded"]), "unavailable_destinations": sum(1 for row in rows if row["unavailable"])}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
