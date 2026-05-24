"""JSON API renderer for profile YAML load health."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.profile_yaml_load_health.v1"
KIND = "max.api.profile_yaml_load_health"
STATUS_RANK = {"failed": 0, "warned": 1, "loaded": 2}


def profile_yaml_load_health_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    profiles = _profiles(payload)
    duplicates = _duplicates(profiles)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(profiles, duplicates),
        "profiles": profiles,
        "missing_required_sections": _missing_sections(profiles),
        "duplicate_profile_ids": duplicates,
        "source_count_summaries": _source_counts(profiles),
        "metadata": _metadata(payload, profiles, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _profiles(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("profiles") if isinstance(payload.get("profiles"), list) else payload.get("results")
    rows = [_profile(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["profile_id"], row["path"]))
    return rows


def _profile(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    errors = _strings(item.get("errors"))
    warnings = _strings(item.get("warnings"))
    missing = _strings(item.get("missing_required_sections", item.get("missing_sections")))
    status = _bucket(item.get("status"), "")
    if errors or missing or status in {"failed", "error"}:
        status = "failed"
    elif warnings or status in {"warned", "warning", "degraded"}:
        status = "warned"
    else:
        status = "loaded"
    return {
        "profile_id": _text(item.get("profile_id") or item.get("id")) or f"profile-{index}",
        "path": _text(item.get("path") or item.get("source")) or "unknown-source",
        "status": status,
        "missing_required_sections": missing,
        "warnings": warnings,
        "errors": errors,
        "source_count": _int(item.get("source_count", item.get("sources"))),
    }


def _summary(profiles: list[dict[str, Any]], duplicates: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in profiles)
    status = "unhealthy" if counts["failed"] or duplicates else ("degraded" if counts["warned"] else "healthy")
    return {"status": status, "profile_count": len(profiles), "loaded_count": counts["loaded"], "warned_count": counts["warned"], "failed_count": counts["failed"], "duplicate_profile_id_count": len(duplicates)}


def _duplicates(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    for row in profiles:
        grouped.setdefault(row["profile_id"], []).append(row["path"])
    rows = [{"profile_id": profile_id, "count": len(paths), "paths": sorted(paths)} for profile_id, paths in grouped.items() if len(paths) > 1]
    rows.sort(key=lambda row: row["profile_id"])
    return rows


def _missing_sections(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [{"profile_id": row["profile_id"], "sections": row["missing_required_sections"]} for row in profiles if row["missing_required_sections"]]
    rows.sort(key=lambda row: row["profile_id"])
    return rows


def _source_counts(profiles: list[dict[str, Any]]) -> dict[str, int]:
    counts = [row["source_count"] for row in profiles]
    return {"min": min(counts) if counts else 0, "max": max(counts) if counts else 0, "total": sum(counts)}


def _metadata(payload: Mapping[str, Any], profiles: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "profile_count": len(profiles)}


def _strings(value: Any) -> list[str]:
    return sorted({_text(item) for item in value if _text(item)}) if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
