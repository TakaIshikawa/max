"""Customer value realization export."""

from __future__ import annotations

import json
from typing import Any

SCHEMA_VERSION = "max.customer_value_realization.v1"
KIND = "max.customer_value_realization"
_STATUS_ORDER = {"at_risk": 0, "partial": 1, "realized": 2, "unknown": 3}


def export_customer_value_realization(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [_row(record) for record in records]
    rows.sort(key=lambda row: (_STATUS_ORDER[row["realization_status"]], row["account_name"].lower()))
    return rows


def render_customer_value_realization_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def _row(record: dict[str, Any]) -> dict[str, Any]:
    target = _text(record.get("target_outcome") or record.get("success_criteria") or record.get("promised_outcome") or "Unknown")
    outcomes = _items(record.get("achieved_outcomes") or record.get("outcomes"))
    evidence = _items(record.get("evidence") or record.get("evidence_ids"))
    usage = _items(record.get("usage_signals") or record.get("usage"))
    gaps = _gaps(target, outcomes, record)
    status = _status(target, outcomes, usage, gaps, record)
    return {
        "account_name": _text(record.get("account_name") or record.get("account") or "Unknown"),
        "target_outcome": target,
        "achieved_outcomes": outcomes or ["none"],
        "current_evidence": evidence,
        "usage_signals": usage or ["unknown"],
        "renewal_context": _text(record.get("renewal_context") or record.get("renewal_date") or ""),
        "realization_status": status,
        "gap_summary": gaps or "No material value gap identified.",
        "recommended_next_step": _text(record.get("next_action") or _next_step(status)),
    }


def _status(target: str, outcomes: list[str], usage: list[str], gaps: str, record: dict[str, Any]) -> str:
    explicit = _text(record.get("realization_status") or record.get("status")).lower().replace(" ", "_")
    if explicit in _STATUS_ORDER:
        return explicit
    usage_text = " ".join(usage).lower()
    if target == "Unknown" and not outcomes:
        return "unknown"
    if gaps or any(word in usage_text for word in ("low", "declining", "inactive")):
        return "at_risk"
    if outcomes and any(word in usage_text for word in ("growing", "active", "adopted", "healthy")):
        return "realized"
    return "partial"


def _gaps(target: str, outcomes: list[str], record: dict[str, Any]) -> str:
    explicit = _text(record.get("gap_summary") or record.get("gaps"))
    if explicit:
        return explicit
    if target != "Unknown" and not outcomes:
        return f"No achieved outcome recorded for {target}."
    return ""


def _next_step(status: str) -> str:
    return {
        "at_risk": "Create value recovery plan with customer sponsor.",
        "partial": "Validate remaining success criteria and capture proof points.",
        "realized": "Package evidence for renewal and expansion conversation.",
        "unknown": "Document target outcome and baseline value evidence.",
    }[status]


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({_text(item) for item in value if _text(item)})
    if isinstance(value, str):
        return sorted({item.strip() for item in value.replace(";", ",").split(",") if item.strip()})
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
