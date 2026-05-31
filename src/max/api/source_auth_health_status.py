"""JSON API renderer for source authentication health status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.source_auth_health_status.v1"
KIND = "max.api.source_auth_health_status"


def source_auth_health_status_to_json(
    payload: Mapping[str, Any],
    *,
    now: str | datetime | None = None,
    expiring_soon_seconds: int | None = None,
    recent_error_seconds: int | None = None,
) -> str:
    as_of = parse_datetime(now) or datetime.now(timezone.utc)
    expiry_window = _int(expiring_soon_seconds if expiring_soon_seconds is not None else payload.get("expiring_soon_seconds"), 86400)
    error_window = _int(recent_error_seconds if recent_error_seconds is not None else payload.get("recent_error_seconds"), 3600)
    rows = [_row(item, as_of, expiry_window, error_window) for item in _items(payload)]
    rows.sort(key=lambda row: (row["severity_rank"], row["source"]))
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows, expiry_window, error_window), "rows": rows, "metadata": source_metadata(payload, source_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    source = payload.get("credentials") if isinstance(payload.get("credentials"), list) else payload.get("sources")
    return [item for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []


def _row(item: Mapping[str, Any], as_of: datetime, expiry_window: int, error_window: int) -> dict[str, Any]:
    expires_at = parse_datetime(item.get("expires_at") or item.get("expiry_at"))
    seconds_until_expiry = int((expires_at - as_of).total_seconds()) if expires_at else None
    last_error_at = parse_datetime(item.get("last_auth_error_at") or item.get("last_error_at"))
    recent_error = bool(item.get("last_auth_error") or item.get("auth_error")) and (last_error_at is None or int((as_of - last_error_at).total_seconds()) <= error_window)
    configured = _bool(item.get("configured", item.get("has_credentials", item.get("present"))), default=True)
    if not configured:
        state = "missing"
    elif recent_error:
        state = "error"
    elif seconds_until_expiry is not None and seconds_until_expiry <= 0:
        state = "expired"
    elif seconds_until_expiry is not None and seconds_until_expiry <= expiry_window:
        state = "expiring_soon"
    else:
        state = "valid"
    severity = "critical" if state in {"missing", "expired", "error"} else "warn" if state == "expiring_soon" else "healthy"
    return {"source": _text(item.get("source") or item.get("source_name") or item.get("name"), "unknown_source"), "credential_state": state, "expires_at": expires_at.isoformat().replace("+00:00", "Z") if expires_at else None, "seconds_until_expiry": seconds_until_expiry, "last_auth_error": item.get("last_auth_error") or item.get("auth_error"), "recent_auth_error": recent_error, "severity": severity, "severity_rank": {"critical": 0, "warn": 1, "healthy": 2}[severity]}


def _summary(rows: list[dict[str, Any]], expiry_window: int, error_window: int) -> dict[str, Any]:
    severity = "critical" if any(row["severity"] == "critical" for row in rows) else "warn" if any(row["severity"] == "warn" for row in rows) else "healthy"
    states = {state: sum(1 for row in rows if row["credential_state"] == state) for state in ("valid", "missing", "expired", "expiring_soon", "error")}
    return {"severity": severity, "source_count": len(rows), "state_counts": states, "expiring_soon_seconds": expiry_window, "recent_error_seconds": error_window}


def _bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "present", "valid"}
    return bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any, default: str) -> str:
    return " ".join(str(value).strip().split()) if value not in (None, "") else default
