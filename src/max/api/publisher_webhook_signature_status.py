"""JSON API renderer for publisher webhook signature status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.publisher_webhook_signature_status.v1"
KIND = "max.api.publisher_webhook_signature_status"
RANK = {"critical": 0, "warning": 1, "unknown": 2, "healthy": 3}


def publisher_webhook_signature_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = parse_datetime(as_of) or parse_datetime(payload.get("as_of"))
    rows = [_row(item, index, now) for index, item in enumerate(list_of_maps(payload.get("destinations") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (RANK[row["status"]], row["provider"], row["destination_id"]))
    affected = [row for row in rows if row["status"] != "healthy"]
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": _overall(rows), "destination_count": len(rows), "affected_destination_count": len(affected), "critical_count": sum(1 for row in rows if row["status"] == "critical"), "warning_count": sum(1 for row in rows if row["status"] == "warning")}, "affected_destinations": affected, "destinations": rows, "actions": _actions(affected), "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, as_of: datetime | None) -> dict[str, Any]:
    failures = int_or_zero(item.get("verification_failures"))
    algorithm = str(item.get("signature_algorithm") or "").lower()
    required = str(item.get("required_algorithm") or "").lower()
    rotation_due = parse_datetime(item.get("rotation_due_at"))
    secret_present = bool(item.get("secret_ref"))
    reasons: list[str] = []
    if not secret_present:
        reasons.append("missing_secret")
    if failures >= 3:
        reasons.append("verification_failures")
    if required and algorithm != required:
        reasons.append("weak_algorithm")
    if rotation_due and as_of and (rotation_due - as_of).days <= 14:
        reasons.append("rotation_due_soon")
    status = "critical" if {"missing_secret", "verification_failures"} & set(reasons) else ("warning" if reasons else "healthy")
    return {"destination_id": str(item.get("destination_id") or item.get("id") or f"destination-{index}"), "provider": str(item.get("provider") or "unknown"), "signature_algorithm": algorithm or None, "required_algorithm": required or None, "signing_secret_configured": secret_present, "last_verified_at": item.get("last_verified_at"), "verification_failures": failures, "rotation_due_at": item.get("rotation_due_at"), "status": status, "reasons": reasons, "action": _action(status)}


def _overall(rows: list[dict[str, Any]]) -> str:
    for status in ("critical", "warning", "unknown"):
        if any(row["status"] == status for row in rows):
            return status
    return "healthy"


def _action(status: str) -> str:
    return {"critical": "restore webhook signing secret and verify recent signatures", "warning": "upgrade signature algorithm or rotate signing secret before due date"}.get(status, "none")


def _actions(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({_action(row["status"]) for row in rows if row["status"] != "healthy"})
