"""JSON API renderer for signal source credential status."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.signal_source_credential_status.v1"
KIND = "max.api.signal_source_credential_status"
STATUS_RANK = {"expired": 0, "missing": 1, "expiring_soon": 2, "valid": 3}


def signal_source_credential_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    credentials = _credentials(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(credentials),
        "credentials": credentials,
        "action_required": [row for row in credentials if row["action_required"]],
        "next_actions": _next_actions(credentials),
        "metadata": _metadata(payload, credentials, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _credentials(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("credentials") if isinstance(payload.get("credentials"), list) else payload.get("source_credentials")
    rows = [_credential(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (not row["action_required"], row["source"], row["provider"], row["adapter"], STATUS_RANK[row["status"]]))
    return rows


def _credential(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    days = _optional_int(item.get("days_until_expiry", item.get("days_to_expiry")))
    status = _status(item.get("status"), days, item.get("missing"))
    return {
        "id": _text(item.get("id") or item.get("credential_id")) or f"credential-{index}",
        "source": _text(item.get("source") or item.get("source_name")) or f"source-{index}",
        "adapter": _text(item.get("adapter") or item.get("adapter_name")) or "unknown-adapter",
        "provider": _text(item.get("provider") or item.get("vendor")) or "unknown-provider",
        "status": status,
        "expires_at": item.get("expires_at") or item.get("expiration_at"),
        "last_rotated_at": item.get("last_rotated_at") or item.get("rotated_at"),
        "days_until_expiry": days,
        "action_required": status in {"expired", "missing", "expiring_soon"},
    }


def _status(value: Any, days: int | None, missing: Any) -> str:
    raw = _text(value).lower().replace("-", "_")
    if raw in STATUS_RANK:
        return raw
    if _bool(missing):
        return "missing"
    if days is not None:
        if days < 0:
            return "expired"
        if days <= 14:
            return "expiring_soon"
    return "valid"


def _summary(credentials: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in credentials)
    return {
        "credential_count": len(credentials),
        "expired_count": counts["expired"],
        "expiring_soon_count": counts["expiring_soon"],
        "missing_count": counts["missing"],
        "valid_count": counts["valid"],
        "action_required_count": sum(1 for row in credentials if row["action_required"]),
    }


def _next_actions(credentials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": f"rotate-{row['id']}", "credential_id": row["id"], "source": row["source"], "provider": row["provider"], "action": f"Resolve {row['status']} credential"}
        for row in credentials
        if row["action_required"]
    ]


def _metadata(payload: Mapping[str, Any], credentials: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "credential_count": len(credentials)}


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "missing"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
