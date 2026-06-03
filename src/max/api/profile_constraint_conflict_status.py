"""JSON API renderer for profile constraint conflict status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.profile_constraint_conflict_status.v1"
KIND = "max.api.profile_constraint_conflict_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def profile_constraint_conflict_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = sorted([_row(item, index) for index, item in enumerate(_items(payload), start=1)], key=lambda row: (STATUS_RANK[row["status"]], -row["conflict_count"], row["profile"]))
    summary = _summary(rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": summary["status"], "summary": summary, "profiles": rows, "metadata": source_metadata(payload, profile_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("profiles") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    conflicts = max(0, int_or_zero(item.get("conflict_count")))
    unresolved = max(0, int_or_zero(item.get("unresolved_conflict_count")))
    status = "critical" if unresolved else "warning" if conflicts else "ok"
    return {"profile": _text(item.get("profile")) or f"profile-{index}", "constraint_count": max(0, int_or_zero(item.get("constraint_count"))), "conflict_count": conflicts, "unresolved_conflict_count": unresolved, "affected_sources": strings(item.get("affected_sources")), "affected_categories": strings(item.get("affected_categories")), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    unresolved_profiles = sum(1 for row in rows if row["unresolved_conflict_count"] > 0)
    conflicted_profiles = sum(1 for row in rows if row["conflict_count"] > 0)
    return {"status": "critical" if unresolved_profiles else "warning" if conflicted_profiles else "ok", "profile_count": len(rows), "conflicted_profile_count": conflicted_profiles, "unresolved_profile_count": unresolved_profiles, "total_conflict_count": sum(row["conflict_count"] for row in rows), "total_unresolved_conflict_count": sum(row["unresolved_conflict_count"] for row in rows)}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
