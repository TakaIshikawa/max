"""Roadmap commitment tracker export."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

SCHEMA_VERSION = "max.roadmap_commitment_tracker.v1"
KIND = "max.roadmap_commitment_tracker"
_AS_OF = date(2026, 1, 1)
_STATUS_ORDER = {"overdue": 0, "at_risk": 1, "on_track": 2, "delivered": 3, "unknown": 4}


def export_roadmap_commitment_tracker(records: list[dict[str, Any]], as_of: str | date | None = None) -> list[dict[str, Any]]:
    anchor = _date(as_of) or _AS_OF
    rows = [_row(record, anchor) for record in records]
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], -row["revenue_exposure"], row["target_date"] or "9999-12-31", row["account_or_segment"].lower()))
    return rows


def render_roadmap_commitment_tracker_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def _row(record: dict[str, Any], anchor: date) -> dict[str, Any]:
    target = _date(record.get("target_date") or record.get("promised_date"))
    delivered = _date(record.get("delivered_date"))
    status = _status(record, target, delivered, anchor)
    slippage = max(((delivered or anchor) - target).days, 0) if target and status in {"overdue", "delivered"} else 0
    return {
        "commitment_owner": _text(record.get("commitment_owner") or record.get("owner") or "Unassigned"),
        "account_or_segment": _text(record.get("account") or record.get("segment") or record.get("account_or_segment") or "Unknown"),
        "promised_capability": _text(record.get("promised_capability") or record.get("capability") or "Unknown"),
        "target_date": target.isoformat() if target else "",
        "status": status,
        "slippage_days": slippage,
        "revenue_exposure": _money(record.get("revenue_exposure") or record.get("arr") or record.get("contract_value")),
        "communication_action": _text(record.get("communication_action") or _action(status)),
    }


def _status(record: dict[str, Any], target: date | None, delivered: date | None, anchor: date) -> str:
    explicit = _text(record.get("status")).lower().replace(" ", "_")
    if explicit in _STATUS_ORDER:
        return explicit
    if delivered:
        return "delivered"
    if not target:
        return "unknown"
    if target < anchor:
        return "overdue"
    if (target - anchor).days <= 30:
        return "at_risk"
    return "on_track"


def _action(status: str) -> str:
    return {
        "overdue": "Send revised delivery date and remediation plan.",
        "at_risk": "Proactively brief customer on delivery confidence.",
        "on_track": "Maintain planned roadmap update cadence.",
        "delivered": "Confirm customer acceptance and close the commitment.",
        "unknown": "Validate target date and owner before next roadmap review.",
    }[status]


def _date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _money(value: Any) -> float:
    try:
        return round(float(str(value or 0).replace(",", "").replace("$", "")), 2)
    except ValueError:
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
