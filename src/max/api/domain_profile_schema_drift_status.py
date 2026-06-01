"""JSON API renderer for domain profile schema drift status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, int_or_zero, list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.domain_profile_schema_drift_status.v1"
KIND = "max.api.domain_profile_schema_drift_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def domain_profile_schema_drift_status_to_json(payload: Mapping[str, Any]) -> str:
    current = _text(payload.get("current_schema_version") or payload.get("schema_current") or "current")
    profiles = [_profile(row, i, current) for i, row in enumerate(list_of_maps(payload.get("profiles") or payload.get("rows")), start=1)]
    status = "critical" if any(row["status"] == "critical" for row in profiles) else ("warning" if any(row["status"] == "warning" for row in profiles) else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "overall_status": status, "current_schema_version": current, "total_profiles": len(profiles), "outdated_profile_count": sum(1 for row in profiles if row["outdated"]), "invalid_profile_count": sum(1 for row in profiles if row["status"] == "critical"), "affected_profiles": sorted([row for row in profiles if row["status"] != "healthy"], key=lambda row: (RANK[row["status"]], row["profile"].casefold())), "profiles": sorted(profiles, key=lambda row: (RANK[row["status"]], row["profile"].casefold())), "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _profile(item: Mapping[str, Any], index: int, current: str) -> dict[str, Any]:
    version = _text(item.get("schema_version") or item.get("version"))
    unknown = version == "" or version == "unknown"
    outdated = bool(version and version != current and not unknown)
    unknown_fields = strings(item.get("unknown_fields"))
    missing_required = strings(item.get("missing_required_fields") or item.get("missing_fields"))
    drift_count = int_or_zero(item.get("drift_count")) or len(unknown_fields) + len(missing_required) + int(outdated or unknown)
    status = "critical" if unknown or missing_required else ("warning" if outdated or unknown_fields else "healthy")
    return {"profile": _text(item.get("profile") or item.get("name") or item.get("id")) or f"profile-{index}", "schema_version": version or "unknown", "outdated": outdated, "unknown_version": unknown, "unknown_fields": unknown_fields, "missing_required_fields": missing_required, "drift_count": drift_count, "status": status, "recommended_action": "repair profile schema fields" if missing_required else ("assign known schema version" if unknown else ("migrate profile to current schema" if outdated else ("remove unknown fields" if unknown_fields else "continue monitoring")))}


def _text(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in as_list(value))
    return " ".join(str(value).strip().split()) if value is not None else ""
