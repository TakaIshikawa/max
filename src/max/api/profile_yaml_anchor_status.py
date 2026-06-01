"""JSON API renderer for profile YAML anchor status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.profile_yaml_anchor_status.v1"
KIND = "max.api.profile_yaml_anchor_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def profile_yaml_anchor_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item, index) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (RANK[row["status"]], row["profile"]))
    affected = [row for row in rows if row["status"] != "healthy"]
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "status": "critical" if any(row["status"] == "critical" for row in rows) else ("warning" if affected else "healthy"),
            "profile_count": len(rows),
            "affected_profile_count": len(affected),
            "unresolved_alias_count": sum(len(row["unresolved_aliases"]) for row in rows),
            "duplicate_anchor_count": sum(len(row["duplicate_anchors"]) for row in rows),
            "unused_anchor_count": sum(len(row["unused_anchors"]) for row in rows),
        },
        "profiles": rows,
        "affected_profiles": affected,
        "actions": _actions(affected),
        "metadata": source_metadata(payload),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = list_of_maps(payload.get("profiles") or payload.get("documents") or payload.get("rows"))
    if not rows and isinstance(payload.get("profile"), Mapping):
        rows = [payload["profile"]]  # type: ignore[list-item]
    return rows


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    anchors = strings(item.get("anchors"))
    aliases = strings(item.get("aliases"))
    unresolved = strings(item.get("unresolved_aliases"))
    duplicates = strings(item.get("duplicate_anchors"))
    unused = sorted(set(anchors) - set(aliases))
    status = "critical" if unresolved or duplicates else ("warning" if unused else "healthy")
    return {
        "profile": str(item.get("profile") or item.get("profile_id") or item.get("id") or f"profile-{index}"),
        "anchors": anchors,
        "aliases": aliases,
        "unresolved_aliases": unresolved,
        "duplicate_anchors": duplicates,
        "unused_anchors": unused,
        "status": status,
        "action": _action(status),
    }


def _action(status: str) -> str:
    return {
        "critical": "fix unresolved aliases or duplicate YAML anchors before loading the profile",
        "warning": "remove unused anchors or add aliases that reference them",
    }.get(status, "none")


def _actions(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({_action(row["status"]) for row in rows if row["status"] != "healthy"})
