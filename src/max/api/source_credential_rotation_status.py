"""JSON API renderer for source credential rotation status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, mapping, source_metadata

SCHEMA_VERSION = "max.api.source_credential_rotation_status.v1"
KIND = "max.api.source_credential_rotation_status"


def source_credential_rotation_status_to_json(payload: Mapping[str, Any]) -> str:
    credentials = _credentials(payload)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "summary": {
                "credential_count": len(credentials),
                "expired_count": sum(1 for row in credentials if row["severity"] == "expired"),
                "blocked_count": sum(1 for row in credentials if row["blocked_reason"]),
            },
            "credentials": credentials,
            "metadata": source_metadata(payload, credential_count=len(credentials)),
        },
        indent=2,
        sort_keys=True,
    )


def _credentials(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("credentials")
    if not isinstance(source, list):
        source = payload.get("source_credentials")
    rows = [_credential(item, index) for index, item in enumerate(list_of_maps(source), start=1)]
    return sorted(rows, key=lambda row: (_severity_rank(row["severity"]), row["source"], row["credential_id"]))


def _credential(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    days = int_or_zero(item.get("days_until_expiry") if item.get("days_until_expiry") is not None else item.get("expires_in_days"))
    blocked_reason = item.get("blocked_reason") or item.get("rotation_blocked_reason")
    return {
        "credential_id": item.get("credential_id") or item.get("id") or f"credential-{index}",
        "source": str(item.get("source") or item.get("source_adapter") or "unknown-source"),
        "credential_owner": item.get("credential_owner") or item.get("owner"),
        "days_until_expiry": days,
        "rotation_window": item.get("rotation_window") or item.get("window"),
        "blocked_reason": blocked_reason,
        "severity": _severity(days, blocked_reason),
        "metadata": dict(mapping(item.get("metadata"))),
    }


def _severity(days: int, blocked_reason: Any) -> str:
    if days < 0:
        return "expired"
    if blocked_reason:
        return "blocked"
    if days <= 7:
        return "critical"
    if days <= 30:
        return "warning"
    return "ok"


def _severity_rank(severity: str) -> int:
    return {"expired": 0, "blocked": 1, "critical": 2, "warning": 3, "ok": 4}.get(severity, 5)
