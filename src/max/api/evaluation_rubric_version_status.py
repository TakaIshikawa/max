"""JSON API renderer for evaluation rubric version status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import as_list, datetime_to_string, source_metadata

SCHEMA_VERSION = "max.api.evaluation_rubric_version_status.v1"
KIND = "max.api.evaluation_rubric_version_status"
STATUS_RANK = {"missing": 0, "mixed": 1, "outdated": 2, "current": 3}


def evaluation_rubric_version_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    active = _text(payload.get("active_version", payload.get("rubric_version"))) or "unknown"
    profiles = _profiles(payload, active)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "active_version": active,
        "summary": _summary(profiles),
        "profiles": profiles,
        "affected_profiles": [row["profile"] for row in profiles if row["status"] != "current"],
        "metadata": source_metadata(payload, as_of=datetime_to_string(as_of) if isinstance(as_of, datetime) else as_of, profile_count=len(profiles), active_version=active),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _profiles(payload: Mapping[str, Any], active: str) -> list[dict[str, Any]]:
    source = payload.get("profiles") if isinstance(payload.get("profiles"), list) else payload.get("evaluation_records")
    rows = [_profile(item, index, active) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["profile"], row["dimension"]))


def _profile(item: Mapping[str, Any], index: int, active: str) -> dict[str, Any]:
    versions = sorted({_text(value) for value in as_list(item.get("observed_versions", item.get("versions", item.get("rubric_version")))) if _text(value)})
    missing = not versions
    status = "missing" if missing else ("mixed" if len(versions) > 1 else ("outdated" if versions[0] != active else "current"))
    return {"profile": _text(item.get("profile")) or f"profile-{index}", "dimension": _text(item.get("dimension")) or "overall", "active_version": active, "observed_versions": versions, "evaluation_count": _count(item, versions), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in rows)
    return {"profile_count": len(rows), "current_count": counts["current"], "mixed_count": counts["mixed"], "outdated_count": counts["outdated"], "missing_count": counts["missing"]}


def _count(item: Mapping[str, Any], versions: list[str]) -> int:
    try:
        return max(0, int(float(item.get("evaluation_count", item.get("count", len(versions))) or 0)))
    except (TypeError, ValueError):
        return len(versions)


def _text(value: Any, default: Any = None) -> str:
    raw = default if value is None else value
    return " ".join(str(raw).strip().split()) if raw is not None else ""

