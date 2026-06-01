"""JSON API renderer for publication destination credential scope status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata, strings

SCHEMA_VERSION = "max.api.publication_destination_credential_scope_status.v1"
KIND = "max.api.publication_destination_credential_scope_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def publication_destination_credential_scope_status_to_json(payload: Mapping[str, Any], *, as_of: datetime | str | None = None) -> str:
    checked_at = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    stale_hours = max(0, int_or_zero(payload.get("stale_verification_hours") or payload.get("verification_stale_hours") or 168))
    rows = [_destination(row, i, checked_at, stale_hours) for i, row in enumerate(list_of_maps(payload.get("destinations") or payload.get("items") or payload.get("rows")), start=1)]
    rows = sorted(rows, key=lambda row: (RANK[row["risk_level"]], -(row["verification_age_hours"] or -1), row["destination"].casefold()))
    blocked = sum(1 for row in rows if row["risk_level"] == "critical")
    stale = sum(1 for row in rows if row["stale_verification"])
    status = "critical" if blocked else ("warning" if stale or any(row["extra_actions"] for row in rows) else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": _stamp(checked_at), "status": status, "summary": {"status": status, "destination_count": len(rows), "blocked_destination_count": blocked, "stale_verification_count": stale, "next_destination_to_verify": rows[0]["destination"] if rows and rows[0]["risk_level"] != "healthy" else None}, "destinations": rows, "risky_destinations": [row for row in rows if row["risk_level"] != "healthy"], "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _destination(item: Mapping[str, Any], index: int, as_of: datetime, stale_hours: int) -> dict[str, Any]:
    required = strings(item.get("required_actions") or item.get("required_scopes"))
    granted = strings(item.get("granted_actions") or item.get("granted_scopes") or item.get("actions"))
    allowed = strings(item.get("allowed_actions")) or required
    missing = sorted(set(required) - set(granted))
    extra = sorted(set(granted) - set(allowed))
    verified = parse_datetime(item.get("last_verified_at") or item.get("verified_at"))
    age = round((as_of - verified).total_seconds() / 3600, 2) if verified else None
    stale = age is None or age > stale_hours
    risk = "critical" if missing else ("warning" if extra or stale else "healthy")
    return {"destination": _text(item.get("destination") or item.get("name")) or f"destination-{index}", "credential_id": _text(item.get("credential_id") or item.get("credential")) or "unknown", "required_actions": required, "granted_actions": granted, "missing_actions": missing, "extra_actions": extra, "last_verified_at": _stamp(verified) if verified else None, "verification_age_hours": age, "stale_verification": stale, "risk_level": risk}


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
