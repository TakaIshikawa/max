"""JSON API renderer for profile run readiness."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, source_metadata


SCHEMA_VERSION = "max.api.profile_run_readiness.v1"
KIND = "max.api.profile_run_readiness"
BLOCKING_STATUSES = {"fail", "failed", "blocked", "missing"}
WARNING_STATUSES = {"warn", "warning"}


def profile_run_readiness_to_json(payload: Mapping[str, Any]) -> str:
    profiles = _profiles(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(payload, profiles),
        "profiles": profiles,
        "ready_profiles": _profiles_by_ready(payload, profiles, True),
        "blocked_profiles": _profiles_by_ready(payload, profiles, False),
        "warnings": _warnings(payload, profiles),
        "check_matrix": _check_matrix(payload, profiles),
        "next_actions": _next_actions(payload, profiles),
        "metadata": source_metadata(payload, profile_count=len(profiles)),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _profiles(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("profiles")
    if not isinstance(source, list):
        source = payload.get("profile_readiness")
    rows = [_profile(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    return sorted(rows, key=lambda row: str(row["profile_id"]))


def _profile(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    checks = _checks(item.get("checks"))
    ready = item.get("ready")
    if ready is None:
        ready = not any(check["status"] in BLOCKING_STATUSES for check in checks)
    return {
        "profile_id": item.get("profile_id") or item.get("id") or f"P{index}",
        "name": item.get("name"),
        "ready": bool(ready),
        "checks": checks,
        "blocking_issue_count": sum(1 for check in checks if check["status"] in BLOCKING_STATUSES),
        "warning_count": sum(1 for check in checks if check["status"] in WARNING_STATUSES),
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _checks(value: object) -> list[dict[str, object]]:
    return sorted(
        [
            {
                "check": item.get("check") or item.get("name") or f"check-{index}",
                "status": str(item.get("status") or "unknown").lower(),
                "message": item.get("message") or item.get("reason"),
            }
            for index, item in enumerate(list_of_maps(value), start=1)
        ],
        key=lambda row: str(row["check"]),
    )


def _summary(payload: Mapping[str, Any], profiles: list[dict[str, Any]]) -> dict[str, int]:
    source = mapping(payload.get("summary"))
    return {
        "ready_count": int_or_zero(source.get("ready_count", sum(1 for profile in profiles if profile["ready"]))),
        "blocked_count": int_or_zero(source.get("blocked_count", sum(1 for profile in profiles if not profile["ready"]))),
        "warning_count": int_or_zero(source.get("warning_count", sum(profile["warning_count"] for profile in profiles))),
        "total_count": int_or_zero(source.get("total_count", len(profiles))),
    }


def _profiles_by_ready(payload: Mapping[str, Any], profiles: list[dict[str, Any]], ready: bool) -> list[dict[str, object]]:
    field = "ready_profiles" if ready else "blocked_profiles"
    explicit = list_of_maps(payload.get(field))
    if explicit:
        return sorted([{"profile_id": item.get("profile_id") or item.get("id") or f"P{index}", "name": item.get("name")} for index, item in enumerate(explicit, start=1)], key=lambda row: str(row["profile_id"]))
    return [{"profile_id": profile["profile_id"], "name": profile["name"]} for profile in profiles if profile["ready"] is ready]


def _warnings(payload: Mapping[str, Any], profiles: list[dict[str, Any]]) -> list[dict[str, object]]:
    explicit = list_of_maps(payload.get("warnings"))
    if explicit:
        return sorted([{"profile_id": item.get("profile_id") or item.get("id"), "check": item.get("check") or item.get("name"), "message": item.get("message") or item.get("reason")} for item in explicit], key=lambda row: (str(row["profile_id"]), str(row["check"])))
    return [
        {"profile_id": profile["profile_id"], "check": check["check"], "message": check["message"]}
        for profile in profiles
        for check in profile["checks"]
        if check["status"] in WARNING_STATUSES
    ]


def _check_matrix(payload: Mapping[str, Any], profiles: list[dict[str, Any]]) -> list[dict[str, object]]:
    explicit = list_of_maps(payload.get("check_matrix"))
    if explicit:
        return sorted([{"profile_id": item.get("profile_id") or item.get("id"), "check": item.get("check") or item.get("name"), "status": item.get("status")} for item in explicit], key=lambda row: (str(row["profile_id"]), str(row["check"])))
    return [
        {"profile_id": profile["profile_id"], "check": check["check"], "status": check["status"]}
        for profile in profiles
        for check in profile["checks"]
    ]


def _next_actions(payload: Mapping[str, Any], profiles: list[dict[str, Any]]) -> list[dict[str, object]]:
    explicit = list_of_maps(payload.get("next_actions"))
    if explicit:
        return sorted([{"id": item.get("id") or f"A{index}", "action": item.get("action") or item.get("title"), "profile_id": item.get("profile_id"), "owner": item.get("owner")} for index, item in enumerate(explicit, start=1)], key=lambda row: str(row["id"]))
    return sorted(
        [{"id": f"fix-{profile['profile_id']}", "action": "Resolve profile readiness blockers", "profile_id": profile["profile_id"], "owner": None} for profile in profiles if not profile["ready"]],
        key=lambda row: str(row["id"]),
    )
