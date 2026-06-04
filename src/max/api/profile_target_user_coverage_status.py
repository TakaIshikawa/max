"""JSON API renderer for profile target user coverage status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.profile_target_user_coverage_status.v1"
KIND = "max.api.profile_target_user_coverage_status"
STATUS_RANK = {"critical": 0, "warning": 1, "insufficient_data": 2, "ok": 3}


def profile_target_user_coverage_status_to_json(payload: Mapping[str, Any], *, concentration_threshold: float = 0.7) -> str:
    rows = [_row(item, index, concentration_threshold) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["coverage_ratio"], row["profile"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"profile_count": len(rows), "uncovered_profile_count": sum(1 for row in rows if row["uncovered_target_users"]), "insufficient_data_count": sum(1 for row in rows if row["status"] == "insufficient_data")}, "profile_rows": rows, "metadata": source_metadata(payload, profile_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("profiles") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int, threshold: float) -> dict[str, Any]:
    targets = strings(item.get("target_users") or item.get("personas"))
    idea_users = [_text(value) for value in as_list(item.get("idea_target_users") or item.get("idea_personas") or item.get("generated_target_users"))]
    idea_users = [value for value in idea_users if value]
    covered = sorted(set(targets) & set(idea_users))
    uncovered = sorted(set(targets) - set(idea_users))
    total_mentions = len(idea_users)
    over = sorted(user for user in set(idea_users) if user in targets and total_mentions and idea_users.count(user) / total_mentions >= threshold)
    ratio = len(covered) / len(targets) if targets else 0.0
    status = "insufficient_data" if not targets else "critical" if uncovered else "warning" if over else "ok"
    return {"profile": _text(item.get("profile") or item.get("profile_id")) or f"profile-{index}", "target_user_count": len(targets), "covered_target_users": covered, "uncovered_target_users": uncovered, "overconcentrated_target_users": over, "coverage_ratio": round(ratio, 4), "status": status}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
