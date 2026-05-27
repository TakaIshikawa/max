"""JSON API renderer for source credential expiry status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, source_metadata

SCHEMA_VERSION = "max.api.source_credential_expiry_status.v1"
KIND = "max.api.source_credential_expiry_status"
STATUS_RANK = {"expired": 0, "expiring_soon": 1, "valid": 2}


def source_credential_expiry_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = _rows(payload)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "metadata": source_metadata(payload, credential_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("credentials") if isinstance(payload.get("credentials"), list) else payload.get("items")
    rows = [_row(item) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (STATUS_RANK[row["status"]], row["source"], row["credential_name"]))


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    days = int_or_zero(item.get("days_until_expiry"))
    warning = max(0, int_or_zero(item.get("warning_days")))
    expired = days < 0
    soon = not expired and days <= warning
    status = "expired" if expired else ("expiring_soon" if soon else "valid")
    return {"source": _bucket(item.get("source"), "unknown"), "credential_name": _text(item.get("credential_name")) or "unknown", "expires_at": _text(item.get("expires_at")) or None, "days_until_expiry": days, "rotation_owner": _text(item.get("rotation_owner")) or None, "warning_days": warning, "expired": expired, "expiring_soon": soon, "missing_owner": not bool(_text(item.get("rotation_owner"))), "status": status}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "expired" if any(row["expired"] for row in rows) else ("expiring_soon" if any(row["expiring_soon"] for row in rows) else "valid"), "credential_count": len(rows), "expired_count": sum(1 for row in rows if row["expired"]), "expiring_soon_count": sum(1 for row in rows if row["expiring_soon"]), "missing_owner_count": sum(1 for row in rows if row["missing_owner"])}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
