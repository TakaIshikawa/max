"""JSON API renderer for spec export destination status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "max.api.spec_export_destination_status.v1"
KIND = "max.api.spec_export_destination_status"


def spec_export_destination_status_to_json(payload: Mapping[str, Any]) -> str:
    """Render spec export destination readiness as deterministic API JSON."""
    destinations = _destinations(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(destinations),
        "destinations": destinations,
        "counts_by_kind": _counts(destinations, "kind"),
        "metadata": _metadata(payload, destinations),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _summary(destinations: list[dict[str, Any]]) -> dict[str, Any]:
    readiness = Counter(row["readiness"] for row in destinations)
    return {
        "total_destinations": len(destinations),
        "ready_count": readiness["ready"],
        "degraded_count": readiness["degraded"],
        "disabled_count": readiness["disabled"],
    }


def _destinations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("destinations")
    if not isinstance(source, list):
        source = payload.get("export_destinations")
    rows = [
        _destination_row(item, index)
        for index, item in enumerate(source if isinstance(source, list) else [], start=1)
        if isinstance(item, Mapping)
    ]
    return sorted(rows, key=lambda row: (str(row["readiness"]), str(row["kind"]), str(row["name"])))


def _destination_row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    enabled = _bool_or_default(item.get("enabled"), default=True)
    pending = _int_or_zero(item.get("pending_count"))
    last_error = item.get("last_error")
    readiness = "disabled" if not enabled else "degraded" if last_error or pending else "ready"
    return {
        "destination_id": item.get("destination_id") or item.get("id") or f"destination-{index}",
        "name": item.get("name") or f"destination-{index}",
        "kind": str(item.get("kind") or "unknown"),
        "enabled": enabled,
        "last_success_at": item.get("last_success_at"),
        "last_error": last_error,
        "pending_count": pending,
        "readiness": readiness,
        "metadata": dict(_mapping(item.get("metadata"))),
    }


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row[key]) for row in rows).items()))


def _metadata(payload: Mapping[str, Any], destinations: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = dict(_mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version") or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        "destination_count": len(destinations),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bool_or_default(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
