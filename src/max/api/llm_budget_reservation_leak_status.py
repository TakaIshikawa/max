"""JSON API renderer for LLM budget reservation leak status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, list_of_maps, mapping, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.llm_budget_reservation_leak_status.v1"
KIND = "max.api.llm_budget_reservation_leak_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def llm_budget_reservation_leak_status_to_json(records: Any, *, now: str | datetime | None = None, stale_after_minutes: int = 60, warning_leak_ratio: float = 0.1) -> str:
    payload = mapping(records)
    source = payload.get("reservations") or payload.get("records") or payload.get("items") or (records if isinstance(records, list) else [])
    effective_now = parse_datetime(now) or parse_datetime(payload.get("now")) or datetime.now().astimezone()
    rows = [_row(item, index, effective_now, stale_after_minutes, warning_leak_ratio) for index, item in enumerate(list_of_maps(source), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], -row["leaked_amount"], row["reservation_id"]))
    status = _overall(rows)
    active = [row for row in rows if row["active"]]
    reserved = sum(row["reserved_amount"] for row in active)
    leaked = sum(row["leaked_amount"] for row in active)
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "status": status, "summary": {"reservation_count": len(rows), "active_reservation_count": len(active), "stale_active_reservation_count": sum(1 for row in active if row["stale"]), "total_reserved_amount": round(reserved, 4), "total_leaked_amount": round(leaked, 4), "leak_ratio": round(leaked / reserved, 4) if reserved else 0.0, "status": status}, "reservations": rows, "metadata": source_metadata(payload, reservation_count=len(rows), as_of=datetime_to_string(effective_now))}, indent=2, sort_keys=True)


def _row(item: Mapping[str, Any], index: int, now: datetime, stale_after: int, warning_ratio: float) -> dict[str, Any]:
    released_at = parse_datetime(item.get("released_at"))
    state = _text(item.get("status") or item.get("state")).casefold()
    active = released_at is None and state not in {"released", "cancelled", "canceled", "closed"}
    reserved = max(0.0, float_or_zero(item.get("reserved_amount") if item.get("reserved_amount") is not None else item.get("reserved_tokens")))
    spent = max(0.0, float_or_zero(item.get("spent_amount") if item.get("spent_amount") is not None else item.get("consumed_tokens")))
    leaked = max(0.0, reserved - spent) if active else 0.0
    created = parse_datetime(item.get("created_at") or item.get("reserved_at"))
    age = max((now - created).total_seconds() / 60, 0.0) if created else 0.0
    stale = bool(active and created and age >= stale_after)
    ratio = round(leaked / reserved, 4) if reserved else 0.0
    status = "critical" if stale and leaked else ("warning" if active and ratio > warning_ratio else "ok")
    return {"reservation_id": _text(item.get("reservation_id") or item.get("id")) or f"reservation-{index}", "reserved_amount": round(reserved, 4), "spent_amount": round(spent, 4), "leaked_amount": round(leaked, 4), "leak_ratio": ratio, "created_at": datetime_to_string(created), "released_at": datetime_to_string(released_at), "active": active, "stale": stale, "status": status}


def _overall(rows: list[dict[str, Any]]) -> str:
    if any(row["status"] == "critical" for row in rows):
        return "critical"
    if any(row["status"] == "warning" for row in rows):
        return "warning"
    return "ok"


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
