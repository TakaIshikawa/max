"""JSON API renderer for LLM budget reservation status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.llm_budget_reservation_status.v1"
KIND = "max.api.llm_budget_reservation_status"


def llm_budget_reservation_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    reservations = _reservations(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(reservations),
        "reservations": reservations,
        "status_totals": _totals(reservations, "status"),
        "stage_totals": _totals(reservations, "pipeline_stage"),
        "risky_reservations": [row for row in reservations if row["over_reserved"] or row["over_spent"]],
        "metadata": _metadata(payload, reservations, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _reservations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("reservations") if isinstance(payload.get("reservations"), list) else payload.get("budget_reservations")
    rows = [_reservation(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (not (row["over_reserved"] or row["over_spent"]), row["pipeline_stage"], row["model"], row["id"]))
    return rows


def _reservation(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    requested = _int(item.get("requested_tokens"))
    reserved = _int(item.get("reserved_tokens", item.get("tokens_reserved")))
    used = _int(item.get("used_tokens", item.get("tokens_used")))
    cap = _float(item.get("cost_cap_usd", item.get("cost_cap")))
    spent = _float(item.get("spent_usd", item.get("cost_usd")))
    status = _text(item.get("status")).lower() or "reserved"
    ratio = round(used / reserved, 4) if reserved else 0.0
    return {
        "id": _text(item.get("id") or item.get("reservation_id")) or f"reservation-{index}",
        "pipeline_stage": _text(item.get("pipeline_stage") or item.get("stage")) or "unknown-stage",
        "model": _text(item.get("model")) or "unknown-model",
        "requested_tokens": requested,
        "reserved_tokens": reserved,
        "used_tokens": used,
        "remaining_tokens": max(reserved - used, 0),
        "cost_cap_usd": cap,
        "spent_usd": spent,
        "status": status,
        "utilization_ratio": ratio,
        "over_reserved": bool(requested and reserved > requested),
        "over_spent": bool(cap and spent > cap),
    }


def _summary(reservations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "reservation_count": len(reservations),
        "reserved_tokens": sum(row["reserved_tokens"] for row in reservations),
        "used_tokens": sum(row["used_tokens"] for row in reservations),
        "remaining_tokens": sum(row["remaining_tokens"] for row in reservations),
        "risky_count": sum(1 for row in reservations if row["over_reserved"] or row["over_spent"]),
    }


def _totals(reservations: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in reservations:
        grouped[row[field]].append(row)
    return [{field: key, "reservation_count": len(items), "reserved_tokens": sum(item["reserved_tokens"] for item in items), "used_tokens": sum(item["used_tokens"] for item in items)} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], reservations: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "reservation_count": len(reservations)}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return round(max(0.0, float(value or 0)), 4)
    except (TypeError, ValueError):
        return 0.0


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
