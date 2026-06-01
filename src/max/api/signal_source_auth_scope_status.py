"""JSON API renderer for signal source authentication scope status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, parse_datetime, source_metadata, strings

SCHEMA_VERSION = "max.api.signal_source_auth_scope_status.v1"
KIND = "max.api.signal_source_auth_scope_status"
RANK = {"critical": 0, "warning": 1, "healthy": 2}


def signal_source_auth_scope_status_to_json(payload: Mapping[str, Any], *, as_of: datetime | str | None = None) -> str:
    checked_at = parse_datetime(as_of) or parse_datetime(payload.get("as_of")) or datetime.now(timezone.utc)
    window = max(0, int_or_zero(payload.get("expiring_scope_days") or payload.get("warning_days") or 14))
    rows = [_source(row, i, checked_at, window) for i, row in enumerate(list_of_maps(payload.get("sources") or payload.get("items") or payload.get("rows")), start=1)]
    rows = sorted(rows, key=lambda row: (RANK[row["risk_level"]], row["source"].casefold(), row["credential_id"].casefold()))
    critical = sum(1 for row in rows if row["risk_level"] == "critical")
    warning = sum(1 for row in rows if row["risk_level"] == "warning")
    status = "critical" if critical else ("warning" if warning else "healthy")
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "as_of": _stamp(checked_at), "status": status, "summary": {"status": status, "source_count": len(rows), "missing_scope_count": sum(len(row["missing_scopes"]) for row in rows), "overbroad_scope_count": sum(len(row["extra_scopes"]) for row in rows), "expiring_scope_count": sum(1 for row in rows if row["scope_expiring"])}, "sources": rows, "risky_sources": [row for row in rows if row["risk_level"] != "healthy"], "metadata": source_metadata(payload)}, indent=2, sort_keys=True)


def _source(item: Mapping[str, Any], index: int, as_of: datetime, window: int) -> dict[str, Any]:
    required = strings(item.get("required_scopes"))
    granted = strings(item.get("granted_scopes") or item.get("scopes"))
    allowed = strings(item.get("allowed_scopes")) or required
    missing = sorted(set(required) - set(granted))
    extra = sorted(set(granted) - set(allowed))
    expires = parse_datetime(item.get("expires_at") or item.get("scope_expires_at"))
    days = (expires.date() - as_of.date()).days if expires else None
    expiring = days is not None and days <= window
    risk = "critical" if missing else ("warning" if extra or expiring else "healthy")
    return {"source": _text(item.get("source") or item.get("name")) or f"source-{index}", "credential_id": _text(item.get("credential_id") or item.get("credential")) or "unknown", "required_scopes": required, "granted_scopes": granted, "missing_scopes": missing, "extra_scopes": extra, "expires_at": _stamp(expires) if expires else None, "days_until_expiry": days, "scope_expiring": expiring, "risk_level": risk}


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
