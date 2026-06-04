"""JSON API renderer for profile YAML secret reference status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, source_metadata, strings

SCHEMA_VERSION = "max.api.profile_yaml_secret_reference_status.v1"
KIND = "max.api.profile_yaml_secret_reference_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def profile_yaml_secret_reference_status_to_json(payload: Any) -> str:
    payload_map = mapping(payload)
    profiles = _profiles(payload)
    status = _overall_status(profiles)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "summary": {
                "profile_count": len(profiles),
                "profiles_with_plaintext_secrets": sum(1 for row in profiles if row["plaintext_secret_count"] > 0),
                "profiles_with_unresolved_references": sum(1 for row in profiles if row["unresolved_reference_count"] > 0),
                "status": status,
            },
            "profiles": profiles,
            "metadata": source_metadata(payload_map, profile_count=len(profiles)),
        },
        indent=2,
        sort_keys=True,
    )


def _profiles(payload: Any) -> list[dict[str, Any]]:
    payload_map = mapping(payload)
    source = payload_map.get("profiles") or payload_map.get("items") or (payload if isinstance(payload, list) else [])
    rows = [_profile(row, index) for index, row in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["profile"]))


def _profile(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    refs = strings(item.get("secret_references"))
    unresolved = strings(item.get("unresolved_references"))
    plaintext_count = max(0, int_or_zero(item.get("plaintext_secret_count")))
    required = max(0, int_or_zero(item.get("required_reference_count")))
    resolved_count = max(0, len(refs) - len(unresolved))
    if plaintext_count > 0:
        status = "critical"
    elif unresolved or resolved_count < required:
        status = "warning"
    else:
        status = "ok"
    return {
        "profile": _text(item.get("profile") or item.get("name")) or f"profile-{index}",
        "secret_references": refs,
        "unresolved_references": unresolved,
        "resolved_reference_count": resolved_count,
        "unresolved_reference_count": len(unresolved),
        "plaintext_secret_count": plaintext_count,
        "required_reference_count": required,
        "status": status,
    }


def _overall_status(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
