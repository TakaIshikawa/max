"""JSON API renderer for publication destination rate limit status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publication_destination_rate_limit_status.v1"
KIND = "max.api.publication_destination_rate_limit_status"
STATUS_RANK = {"exhausted": 0, "near_exhausted": 1, "healthy": 2}


def publication_destination_rate_limit_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item, index) for index, item in enumerate(list_of_maps(payload.get("destinations") or payload.get("quotas") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["remaining"], row["destination"]))
    blocked = [row for row in rows if row["status"] == "exhausted"]
    summary_status = "no_data" if not rows else ("critical" if blocked else ("warning" if any(row["status"] == "near_exhausted" for row in rows) else "healthy"))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": summary_status, "destination_count": len(rows), "blocked_count": len(blocked), "near_exhausted_count": sum(1 for row in rows if row["status"] == "near_exhausted")}, "destinations": rows, "blocked_destinations": blocked, "next_reset": min((row["reset_at"] for row in rows if row["reset_at"] != "unknown"), default="unknown"), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    limit = max(0, int_or_zero(item.get("limit", item.get("quota_limit"))))
    remaining = max(0, int_or_zero(item.get("remaining", item.get("remaining_quota"))))
    rate = round(remaining / limit, 4) if limit else (1.0 if remaining else 0.0)
    status = "exhausted" if remaining <= 0 else ("near_exhausted" if rate <= 0.1 else "healthy")
    return {"destination": str(item.get("destination") or item.get("name") or item.get("id") or f"destination-{index}"), "limit": limit, "remaining": remaining, "remaining_rate": rate, "reset_at": str(item.get("reset_at") or "unknown"), "reset_after_seconds": int_or_zero(item.get("reset_after_seconds")), "retry_after_seconds": int_or_zero(item.get("retry_after_seconds")), "status": status}
