"""JSON API renderer for publisher destination capability."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.publisher_destination_capability.v1"
KIND = "max.api.publisher_destination_capability"


def publisher_destination_capability_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    destinations = _destinations(payload)
    unsupported = _unsupported(payload, destinations)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(destinations, unsupported),
        "destinations": destinations,
        "unsupported_requests": unsupported,
        "auth_warnings": [row for row in destinations if row["auth_status"] not in {"configured", "valid"}],
        "rate_limit_warnings": [row for row in destinations if row["rate_limit_posture"] in {"limited", "exhausted", "unknown"}],
        "metadata": _metadata(payload, destinations, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _destinations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("destinations") if isinstance(payload.get("destinations"), list) else payload.get("configured_destinations")
    rows = [_destination(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (row["destination"], row["auth_status"]))
    return rows


def _destination(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "destination": _text(item.get("destination") or item.get("name") or item.get("target_type")) or f"destination-{index}",
        "supported_artifact_types": _sorted_unique(item.get("supported_artifact_types") or item.get("artifact_types")),
        "capabilities": _sorted_unique(item.get("capabilities")),
        "auth_status": _text(item.get("auth_status") or item.get("auth")).lower() or "unknown",
        "rate_limit_posture": _text(item.get("rate_limit_posture") or item.get("rate_limit")).lower() or "unknown",
        "dry_run_supported": _bool(item.get("dry_run_supported", item.get("supports_dry_run"))),
        "last_success_at": item.get("last_success_at"),
        "last_failure_at": item.get("last_failure_at"),
    }


def _unsupported(payload: Mapping[str, Any], destinations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configured = {row["destination"]: row for row in destinations}
    requested = _sorted_unique(payload.get("requested_destinations") or payload.get("requested"))
    rows = []
    for value in requested:
        if value not in configured:
            rows.append({"destination": value, "reason": "destination is not configured", "action": "configure publisher destination"})
    rows.sort(key=lambda row: row["destination"])
    return rows


def _summary(destinations: list[dict[str, Any]], unsupported: list[dict[str, Any]]) -> dict[str, Any]:
    auth_counts = Counter(row["auth_status"] for row in destinations)
    return {
        "destination_count": len(destinations),
        "unsupported_request_count": len(unsupported),
        "auth_warning_count": sum(1 for row in destinations if row["auth_status"] not in {"configured", "valid"}),
        "rate_limit_warning_count": sum(1 for row in destinations if row["rate_limit_posture"] in {"limited", "exhausted", "unknown"}),
        "configured_auth_count": auth_counts["configured"] + auth_counts["valid"],
    }


def _metadata(payload: Mapping[str, Any], destinations: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "destination_count": len(destinations)}


def _sorted_unique(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({_text(item) for item in value if _text(item)})
    if value in (None, ""):
        return []
    return [_text(value)]


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
