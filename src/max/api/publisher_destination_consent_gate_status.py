"""JSON API renderer for publisher destination consent gate status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import bool_or_default, int_or_zero, list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.publisher_destination_consent_gate_status.v1"
KIND = "max.api.publisher_destination_consent_gate_status"


def publisher_destination_consent_gate_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(row) for row in _items(payload)]
    rows.sort(key=lambda row: (row["status"] != "blocked", row["destination"], row["profile"]))
    blocked = sum(row["blocked_specs"] for row in rows)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": "blocked" if blocked else "ok", "summary": {"destination_count": len(rows), "blocked_specs": blocked, "blocked_row_count": sum(1 for row in rows if row["status"] == "blocked")}, "destinations": rows, "metadata": source_metadata(payload, destination_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("destinations")) or list_of_maps(payload.get("items"))


def _row(row: Mapping[str, Any]) -> dict[str, Any]:
    requires = bool_or_default(row.get("requires_consent"), default=False)
    recorded = bool_or_default(row.get("consent_recorded"), default=False)
    pending = max(0, int_or_zero(row.get("pending_specs")))
    blocked = requires and not recorded
    return {"destination": _bucket(row.get("destination"), "unknown_destination"), "profile": _bucket(row.get("profile"), "unknown_profile"), "requires_consent": requires, "consent_recorded": recorded, "pending_specs": pending, "blocked_specs": pending if blocked else 0, "last_consent_at": _text(row.get("last_consent_at")) or None, "status": "blocked" if blocked else "ok"}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
