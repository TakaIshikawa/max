"""JSON API renderer for source adapter credential expiry status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.source_adapter_credential_expiry_status.v1"
KIND = "max.api.source_adapter_credential_expiry_status"


def source_adapter_credential_expiry_status_to_json(payload: Mapping[str, Any]) -> str:
    warning_days = max(0, int_or_zero(payload.get("warning_days") or 14))
    critical_days = max(0, int_or_zero(payload.get("critical_days") or 3))
    rows = [_row(item, index, warning_days, critical_days) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (_rank(row["status"]), row["days_until_expiry"], row["adapter"]))
    status = rows[0]["status"] if rows else "ok"
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "status": status,
            "adapter_count": len(rows),
            "expired_count": sum(1 for row in rows if row["status"] == "critical" and row["days_until_expiry"] < 0),
            "expiring_count": sum(1 for row in rows if row["status"] in {"critical", "warning"} and row["days_until_expiry"] >= 0),
            "worst_adapter": rows[0]["adapter"] if rows else None,
            "warning_days": warning_days,
            "critical_days": critical_days,
            "adapters": rows,
            "metadata": source_metadata(payload, adapter_count=len(rows)),
        },
        indent=2,
        sort_keys=True,
    )


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("adapters") or payload.get("credentials") or payload.get("items") or payload.get("rows"))


def _row(item: Mapping[str, Any], index: int, warning_days: int, critical_days: int) -> dict[str, Any]:
    days = int_or_zero(item.get("days_until_expiry"))
    status = "critical" if days < 0 or days <= critical_days else "warning" if days <= warning_days else "ok"
    return {
        "adapter": _text(item.get("adapter") or item.get("source")) or f"adapter-{index}",
        "credential_name": _text(item.get("credential_name") or item.get("credential")) or "unknown",
        "days_until_expiry": days,
        "expires_at": _text(item.get("expires_at")) or None,
        "status": status,
    }


def _rank(status: str) -> int:
    return {"critical": 0, "warning": 1, "ok": 2}.get(status, 3)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
