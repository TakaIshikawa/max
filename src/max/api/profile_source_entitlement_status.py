"""JSON API renderer for profile source entitlement status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.profile_source_entitlement_status.v1"
KIND = "max.api.profile_source_entitlement_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def profile_source_entitlement_status_to_json(payload: Mapping[str, Any]) -> str:
    available = set(strings(payload.get("available_entitlements") or payload.get("entitlements")))
    restricted = set(strings(payload.get("restricted_sources")))
    profiles = [_profile(item, index, available, restricted) for index, item in enumerate(list_of_maps(payload.get("profiles") or payload.get("rows")), start=1)]
    profiles.sort(key=lambda row: (RANK[row["status"]], row["profile"]))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": "critical" if any(row["status"] == "critical" for row in profiles) else ("warning" if any(row["status"] == "warning" for row in profiles) else "healthy"), "profile_count": len(profiles), "missing_entitlement_count": sum(len(row["missingEntitlements"]) for row in profiles), "restricted_source_count": sum(len(row["restrictedSources"]) for row in profiles)}, "profiles": profiles, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _profile(item: Mapping[str, Any], index: int, available: set[str], restricted: set[str]) -> dict[str, Any]:
    requested = set(strings(item.get("requested_sources") or item.get("sources")))
    allowed = sorted(requested & available - restricted)
    missing = sorted(requested - available)
    blocked = sorted(requested & restricted)
    status = "critical" if missing else ("warning" if blocked else "healthy")
    return {"profile": str(item.get("profile") or item.get("profile_id") or f"profile-{index}"), "requestedSources": sorted(requested), "allowedSources": allowed, "missingEntitlements": missing, "restrictedSources": blocked, "status": status}
