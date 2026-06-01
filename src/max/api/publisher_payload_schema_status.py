"""JSON API renderer for publisher payload schema status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.publisher_payload_schema_status.v1"
KIND = "max.api.publisher_payload_schema_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def publisher_payload_schema_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = parse_datetime(as_of) or parse_datetime(payload.get("as_of"))
    rows = [_row(item, index, now) for index, item in enumerate(list_of_maps(payload.get("destinations") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (RANK[row["status"]], row["destination_id"]))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if any(row["status"] == "warning" for row in rows) else "healthy"), "destination_count": len(rows), "invalid_destination_count": sum(1 for row in rows if row["status"] == "critical"), "stale_destination_count": sum(1 for row in rows if row["stale"])}, "destinations": rows, "affected_destinations": [row for row in rows if row["status"] != "healthy"], "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    checked_at = parse_datetime(item.get("last_validated_at") or item.get("validated_at"))
    stale_after = int_or_zero(item.get("stale_after_days") or 7)
    stale = bool(checked_at and as_of and (as_of - checked_at).days > stale_after)
    result = str(item.get("last_validation_result") or item.get("validation_result") or "").lower()
    errors = int_or_zero(item.get("error_count"))
    status = str(item.get("status") or ("critical" if result in {"failed", "invalid", "error"} or errors else ("warning" if stale else "healthy")))
    return {"destination_id": str(item.get("destination_id") or item.get("id") or f"destination-{index}"), "publisher": item.get("publisher"), "schema_version": item.get("schema_version"), "last_validation_result": result or None, "error_count": errors, "last_validated_at": item.get("last_validated_at") or item.get("validated_at"), "stale": stale, "status": status}
