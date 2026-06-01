"""JSON API renderer for profile constraint violation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.profile_constraint_violation_status.v1"
KIND = "max.api.profile_constraint_violation_status"


def profile_constraint_violation_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item, index) for index, item in enumerate(list_of_maps(payload.get("violations") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (not row["blocking"], row["profile"], row["constraint_type"], row["violation_id"]))
    blocking = [row for row in rows if row["blocking"]]
    status = "no_data" if not rows else ("critical" if blocking else "warning")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "violation_count": len(rows), "blocking_count": len(blocking), "advisory_count": len(rows) - len(blocking), "repeated_constraint_types": _repeated(rows)}, "violations": rows, "profiles": _profiles(rows), "blocking_violations": blocking, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    severity = str(item.get("severity") or item.get("level") or "").lower()
    blocking = bool(item.get("blocking")) or severity in {"blocking", "critical", "error"}
    return {"violation_id": str(item.get("violation_id") or item.get("id") or f"violation-{index}"), "profile": str(item.get("profile") or item.get("profile_id") or "unknown_profile"), "constraint_type": str(item.get("constraint_type") or item.get("type") or "unknown_constraint"), "blocking": blocking, "severity": "blocking" if blocking else "advisory", "message": item.get("message")}


def _repeated(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    types = sorted({row["constraint_type"] for row in rows})
    return [{"constraint_type": value, "count": count} for value in types if (count := sum(1 for row in rows if row["constraint_type"] == value)) > 1]


def _profiles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles = sorted({row["profile"] for row in rows})
    return [{"profile": profile, "violation_count": sum(1 for row in rows if row["profile"] == profile), "blocking_count": sum(1 for row in rows if row["profile"] == profile and row["blocking"]), "constraint_types": sorted({row["constraint_type"] for row in rows if row["profile"] == profile})} for profile in profiles]
