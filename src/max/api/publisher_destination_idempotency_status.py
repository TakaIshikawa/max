"""JSON API renderer for publisher destination idempotency status."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publisher_destination_idempotency_status.v1"
KIND = "max.api.publisher_destination_idempotency_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def publisher_destination_idempotency_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"destination_count": len({row["destination"] for row in rows}), "duplicate_keys": sum(1 for row in rows if row["duplicate_count"] > 0), "conflicting_keys": sum(1 for row in rows if row["status"] == "critical"), "critical_destinations": len({row["destination"] for row in rows if row["status"] == "critical"})}, "destination_rows": rows, "metadata": source_metadata(payload, idempotency_group_count=len(rows))}, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for index, item in enumerate(list_of_maps(payload.get("destinations") or payload.get("rows") or payload.get("items")), start=1):
        destination = _text(item.get("destination")) or f"destination-{index}"
        key = _text(item.get("idempotency_key") or item.get("key"))
        grouped[(destination, key)].append(item)
    rows = [_row(destination, key, items) for (destination, key), items in grouped.items()]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], -row["duplicate_count"], row["destination"], row["idempotency_key"]))


def _row(destination: str, key: str, items: list[Mapping[str, Any]]) -> dict[str, Any]:
    attempts = sum(max(1, int_or_zero(item.get("attempts", 1))) for item in items)
    explicit_duplicates = sum(max(0, int_or_zero(item.get("duplicate_count"))) for item in items)
    duplicate_count = max(explicit_duplicates, len(items) - 1)
    artifact_ids = sorted({_text(item.get("published_artifact_id")) for item in items if _text(item.get("published_artifact_id"))})
    status = "critical" if len(artifact_ids) > 1 else "warning" if not key or duplicate_count else "ok"
    return {"destination": destination, "idempotency_key": key or None, "attempt_count": attempts, "duplicate_count": duplicate_count, "artifact_ids": artifact_ids, "last_statuses": sorted({_text(item.get("last_status")) for item in items if _text(item.get("last_status"))}), "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
