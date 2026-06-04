"""JSON API renderer for publication destination failover readiness."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.publication_destination_failover_readiness_status.v1"
KIND = "max.api.publication_destination_failover_readiness_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def publication_destination_failover_readiness_status_to_json(payload: Any, *, max_drill_age_days: int = 30) -> str:
    payload_map = mapping(payload)
    destinations = _destinations(payload, max_drill_age_days=max_drill_age_days)
    status = _overall_status(destinations)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "summary": {
                "destination_count": len(destinations),
                "critical_destination_count": sum(1 for row in destinations if row["status"] == "critical"),
                "warning_destination_count": sum(1 for row in destinations if row["status"] == "warning"),
                "queued_publication_count": sum(row["queued_publications"] for row in destinations),
                "status": status,
            },
            "destinations": destinations,
            "metadata": source_metadata(payload_map, destination_count=len(destinations)),
        },
        indent=2,
        sort_keys=True,
    )


def _destinations(payload: Any, *, max_drill_age_days: int) -> list[dict[str, Any]]:
    payload_map = mapping(payload)
    source = payload_map.get("destinations") or payload_map.get("items") or (payload if isinstance(payload, list) else [])
    rows = [_destination(row, index, max_drill_age_days) for index, row in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["queued_publications"], row["destination"]))


def _destination(item: Mapping[str, Any], index: int, max_drill_age_days: int) -> dict[str, Any]:
    primary_available = _bool(item.get("primary_available"), default=True)
    fallback_available = _bool(item.get("fallback_available"), default=False)
    drill_age = max(0, int_or_zero(item.get("failover_drill_age_days")))
    status = _status(primary_available, fallback_available, drill_age, max_drill_age_days)
    return {
        "destination": _text(item.get("destination") or item.get("name")) or f"destination-{index}",
        "primary_available": primary_available,
        "fallback_available": fallback_available,
        "last_failover_minutes": max(0, int_or_zero(item.get("last_failover_minutes"))),
        "queued_publications": max(0, int_or_zero(item.get("queued_publications"))),
        "failover_drill_age_days": drill_age,
        "status": status,
    }


def _status(primary_available: bool, fallback_available: bool, drill_age: int, max_drill_age_days: int) -> str:
    if not primary_available and not fallback_available:
        return "critical"
    if not primary_available or drill_age > max_drill_age_days:
        return "warning"
    return "ok"


def _overall_status(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "available"}
    return bool(value)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
