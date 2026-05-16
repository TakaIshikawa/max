"""Implementation blocker aging export."""

from __future__ import annotations

import json
from typing import Any

SCHEMA_VERSION = "max.implementation_blocker_aging.v1"
KIND = "max.implementation_blocker_aging"
_BUCKET_ORDER = {"90_plus": 0, "31_90": 1, "15_30": 2, "0_14": 3}


def export_implementation_blocker_aging(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [_row(blocker) for blocker in blockers]
    rows.sort(key=lambda row: (_BUCKET_ORDER[row["age_bucket"]], -row["age_days"], row["account"].lower(), row["blocker_summary"].lower()))
    return rows


def render_implementation_blocker_aging_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def _row(blocker: dict[str, Any]) -> dict[str, Any]:
    age = _int(blocker.get("age_days") or blocker.get("days_open"))
    bucket = _bucket(age)
    escalation = _escalation(age, blocker)
    return {
        "account": _text(blocker.get("account") or blocker.get("account_name") or "Unknown"),
        "blocker_summary": _text(blocker.get("summary") or blocker.get("blocker") or "Unknown"),
        "owner": _text(blocker.get("owner") or blocker.get("mitigation_owner") or "Unassigned"),
        "age_days": age,
        "age_bucket": bucket,
        "dependency_type": _text(blocker.get("dependency_type") or blocker.get("dependency") or "unknown"),
        "escalation_status": escalation,
        "recommended_action": _action(escalation, bucket),
    }


def _bucket(age: int) -> str:
    if age >= 90:
        return "90_plus"
    if age >= 31:
        return "31_90"
    if age >= 15:
        return "15_30"
    return "0_14"


def _escalation(age: int, blocker: dict[str, Any]) -> str:
    status = _text(blocker.get("status") or blocker.get("escalation_status")).lower()
    if "escalat" in status or age >= 90:
        return "escalated"
    if age >= 31 or status in {"blocked", "overdue"}:
        return "needs_escalation"
    return "monitor"


def _action(escalation: str, bucket: str) -> str:
    if escalation == "escalated":
        return "Confirm executive owner and unblock path within 48 hours."
    if escalation == "needs_escalation":
        return "Escalate dependency owner and reset implementation date."
    if bucket == "15_30":
        return "Review blocker in weekly implementation checkpoint."
    return "Monitor with assigned implementation owner."


def _int(value: Any) -> int:
    try:
        return max(int(float(str(value or 0))), 0)
    except ValueError:
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
