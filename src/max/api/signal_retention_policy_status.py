"""JSON API renderer for signal retention policy status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.signal_retention_policy_status.v1"
KIND = "max.api.signal_retention_policy_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def signal_retention_policy_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item, index) for index, item in enumerate(list_of_maps(payload.get("policies") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (RANK[row["status"]], row["source"], row["profile"]))
    affected = [row for row in rows if row["status"] != "healthy"]
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if affected else "healthy"), "policy_count": len(rows), "violating_policy_count": len(affected), "expired_count": sum(row["expired_count"] for row in rows)}, "policies": rows, "affected_policies": affected, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    expired = int_or_zero(item.get("expired_count"))
    max_age = int_or_zero(item.get("max_age_days"))
    policy_age = int_or_zero(item.get("policy_age_days"))
    status = str(item.get("status") or ("critical" if expired > 10 or (policy_age and max_age and max_age > policy_age * 2) else ("warning" if expired or (policy_age and max_age > policy_age) else "healthy")))
    return {"source": str(item.get("source") or f"source-{index}"), "profile": str(item.get("profile") or item.get("profile_id") or "default"), "retained_count": int_or_zero(item.get("retained_count")), "expired_count": expired, "max_age_days": max_age, "policy_age_days": policy_age, "status": status}
