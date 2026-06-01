"""JSON API renderer for profile deprecation sunset status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.profile_deprecation_sunset_status.v1"
KIND = "max.api.profile_deprecation_sunset_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def profile_deprecation_sunset_status_to_json(payload: Mapping[str, Any]) -> str:
    as_of = parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    warning_days = int_or_zero(payload.get("warning_days") or 30)
    profiles = [_profile(row, i, as_of, warning_days) for i, row in enumerate(list_of_maps(payload.get("profiles") or payload.get("rows")), start=1)]
    status = "critical" if any(row["status"] == "critical" for row in profiles) else ("warning" if any(row["status"] == "warning" for row in profiles) else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "overall_status": status, "total_profiles": len(profiles), "deprecated_count": sum(1 for row in profiles if row["deprecated"]), "approaching_sunset_count": sum(1 for row in profiles if row["approaching_sunset"]), "overdue_sunset_count": sum(1 for row in profiles if row["overdue_sunset"]), "missing_replacement_count": sum(1 for row in profiles if row["missing_replacement"]), "affected_profiles": sorted([row for row in profiles if row["status"] != "healthy"], key=lambda row: (RANK[row["status"]], row["profile"].casefold())), "profiles": profiles, "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _profile(item: Mapping[str, Any], index: int, as_of: datetime, warning_days: int) -> dict[str, Any]:
    sunset = parse_datetime(item.get("sunset_at") or item.get("sunset_date"))
    days = (sunset.date() - as_of.date()).days if sunset else None
    deprecated = bool(item.get("deprecated", item.get("is_deprecated", sunset is not None)))
    in_use = int_or_zero(item.get("active_usage_count") or item.get("usage_count")) > 0 or bool(item.get("in_use"))
    archive_only = bool(item.get("archive_only"))
    replacement = _text(item.get("replacement_profile") or item.get("replacement"))
    missing = deprecated and not replacement
    overdue = bool(days is not None and days < 0)
    approaching = bool(days is not None and 0 <= days <= warning_days)
    status = "critical" if overdue or missing or (archive_only and in_use) else ("warning" if approaching or deprecated else "healthy")
    return {"profile": _text(item.get("profile") or item.get("name") or item.get("id")) or f"profile-{index}", "deprecated": deprecated, "sunset_at": item.get("sunset_at") or item.get("sunset_date"), "days_to_sunset": days, "approaching_sunset": approaching, "overdue_sunset": overdue, "replacement_profile": replacement, "missing_replacement": missing, "archive_only": archive_only, "active_usage_count": int_or_zero(item.get("active_usage_count") or item.get("usage_count")), "status": status, "recommended_action": "assign replacement profile" if missing else ("stop archive-only profile usage" if archive_only and in_use else ("escalate overdue sunset" if overdue else ("prepare profile sunset" if approaching else "continue monitoring")))}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
