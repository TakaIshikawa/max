"""JSON API renderer for publisher retry idempotency gap status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import float_or_zero, int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.publisher_retry_idempotency_gap_status.v1"
KIND = "max.api.publisher_retry_idempotency_gap_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def publisher_retry_idempotency_gap_status_to_json(
    payload: Any,
    *,
    warning_missing_key_rate: float = 0.05,
    retry_warning_count: int = 3,
) -> str:
    payload_map = mapping(payload)
    destinations = _destinations(payload, warning_missing_key_rate, retry_warning_count)
    status = _overall_status(destinations)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "summary": {
                "destination_count": len(destinations),
                "destinations_with_duplicates": sum(1 for row in destinations if row["duplicate_publication_count"] > 0),
                "total_missing_key_count": sum(row["missing_key_count"] for row in destinations),
                "max_missing_key_rate": max((row["missing_key_rate"] for row in destinations), default=0.0),
                "status": status,
            },
            "destinations": destinations,
            "metadata": source_metadata(payload_map, destination_count=len(destinations)),
        },
        indent=2,
        sort_keys=True,
    )


def _destinations(payload: Any, warning_missing_key_rate: float, retry_warning_count: int) -> list[dict[str, Any]]:
    payload_map = mapping(payload)
    source = payload_map.get("destinations") or payload_map.get("items") or (payload if isinstance(payload, list) else [])
    rows = [_destination(row, index, warning_missing_key_rate, retry_warning_count) for index, row in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["duplicate_publication_count"], -row["missing_key_rate"], row["destination"]))


def _destination(item: Mapping[str, Any], index: int, warning_missing_key_rate: float, retry_warning_count: int) -> dict[str, Any]:
    retry_count = max(0, int_or_zero(item.get("retry_count")))
    key_count = max(0, int_or_zero(item.get("idempotency_key_count")))
    missing = max(0, int_or_zero(item.get("missing_key_count")))
    duplicates = max(0, int_or_zero(item.get("duplicate_publication_count")))
    total = key_count + missing
    missing_rate = round(missing / total, 4) if total else 0.0
    if duplicates > 0:
        status = "critical"
    elif missing_rate > warning_missing_key_rate or retry_count > retry_warning_count:
        status = "warning"
    else:
        status = "ok"
    return {
        "destination": _text(item.get("destination") or item.get("name")) or f"destination-{index}",
        "retry_count": retry_count,
        "idempotency_key_count": key_count,
        "missing_key_count": missing,
        "duplicate_publication_count": duplicates,
        "last_duplicate_age_minutes": max(0.0, float_or_zero(item.get("last_duplicate_age_minutes"))),
        "missing_key_rate": missing_rate,
        "status": status,
    }


def _overall_status(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
