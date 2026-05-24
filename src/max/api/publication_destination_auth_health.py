"""JSON API renderer for publication destination authentication health."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.publication_destination_auth_health.v1"
KIND = "max.api.publication_destination_auth_health"
STATUS_RANK = {"failed_auth": 0, "missing_scope": 1, "expiring": 2, "healthy": 3}


def publication_destination_auth_health_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    now = _date(as_of) or _date(payload.get("as_of")) or datetime.now(timezone.utc)
    warning_days = _int(payload.get("expiry_warning_days", payload.get("warning_window_days", 14)))
    destinations = _destinations(payload, now, warning_days)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(destinations),
        "destinations": destinations,
        "failed_auth_destinations": [row for row in destinations if row["auth_status"] == "failed_auth"],
        "missing_scope_destinations": [row for row in destinations if row["auth_status"] == "missing_scope"],
        "expiring_destinations": [row for row in destinations if row["auth_status"] == "expiring"],
        "safe_to_publish_destinations": [row for row in destinations if row["auth_status"] == "healthy"],
        "reauthorization_actions": _actions(destinations),
        "metadata": _metadata(payload, destinations, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _destinations(payload: Mapping[str, Any], now: datetime, warning_days: int) -> list[dict[str, Any]]:
    source = payload.get("destinations") if isinstance(payload.get("destinations"), list) else payload.get("auth_checks")
    rows = [_destination(item, index, now, warning_days) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["auth_status"]], row["destination"]))
    return rows


def _destination(item: Mapping[str, Any], index: int, now: datetime, warning_days: int) -> dict[str, Any]:
    expires_at = _date(item.get("expires_at") or item.get("token_expires_at") or item.get("expiry"))
    days_until_expiry = (expires_at - now).days if expires_at else None
    missing = _strings(item.get("missing_scopes", item.get("missing_scope")))
    failed = _bool(item.get("failed_auth", item.get("auth_failed", item.get("failed")))) or _text(item.get("status")).lower() in {"failed", "error", "unauthorized"}
    if failed:
        status = "failed_auth"
    elif missing:
        status = "missing_scope"
    elif days_until_expiry is not None and days_until_expiry <= warning_days:
        status = "expiring"
    else:
        status = "healthy"
    return {
        "destination": _text(item.get("destination") or item.get("name")) or f"destination-{index}",
        "auth_status": status,
        "expires_at": expires_at.isoformat().replace("+00:00", "Z") if expires_at else None,
        "days_until_expiry": days_until_expiry,
        "required_scopes": _strings(item.get("required_scopes", item.get("scopes"))),
        "missing_scopes": missing,
        "failure_reason": _text(item.get("failure_reason") or item.get("reason")),
    }


def _actions(destinations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in destinations:
        if row["auth_status"] == "failed_auth":
            rows.append({"destination": row["destination"], "action": "Reauthorize destination", "reason": row["failure_reason"]})
        elif row["auth_status"] == "missing_scope":
            rows.append({"destination": row["destination"], "action": "Grant missing publication scopes", "missing_scopes": row["missing_scopes"]})
        elif row["auth_status"] == "expiring":
            rows.append({"destination": row["destination"], "action": "Refresh credential before expiry", "days_until_expiry": row["days_until_expiry"]})
    return rows


def _summary(destinations: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["auth_status"] for row in destinations)
    return {"destination_count": len(destinations), "healthy_count": counts["healthy"], "expiring_count": counts["expiring"], "missing_scope_count": counts["missing_scope"], "failed_auth_count": counts["failed_auth"]}


def _metadata(payload: Mapping[str, Any], destinations: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "destination_count": len(destinations)}


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    return sorted({_text(item).lower() for item in values if _text(item)})


def _date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
