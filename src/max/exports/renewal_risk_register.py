"""Renewal risk register export."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

SCHEMA_VERSION = "max.renewal_risk_register.v1"
KIND = "max.renewal_risk_register"
_AS_OF = date(2026, 1, 1)
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def export_renewal_risk_register(records: list[dict[str, Any]], as_of: str | date | None = None) -> list[dict[str, Any]]:
    """Return deterministic renewal risk rows from account records."""

    anchor = _date(as_of) or _AS_OF
    rows = [_row(record, anchor) for record in records]
    rows.sort(key=lambda row: (_SEVERITY_ORDER[row["severity"]], row["renewal_date"] or "9999-12-31", row["account_name"].lower()))
    return rows


def render_renewal_risk_register_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def _row(record: dict[str, Any], anchor: date) -> dict[str, Any]:
    renewal = _date(record.get("renewal_date") or record.get("contract_end_date"))
    days = (renewal - anchor).days if renewal else None
    health = _items(record.get("health_indicators") or record.get("health") or record.get("health_signals"))
    incidents = _items(record.get("open_incidents") or record.get("incidents"))
    blockers = _items(record.get("open_blockers") or record.get("blockers"))
    drivers = _risk_drivers(days, health, incidents, blockers, record)
    severity = _severity(days, health, incidents, blockers, record)
    return {
        "account_name": _text(record.get("account_name") or record.get("customer") or record.get("name") or "Unknown"),
        "renewal_date": renewal.isoformat() if renewal else "",
        "days_to_renewal": days,
        "arr": _money(record.get("arr") if record.get("arr") is not None else record.get("contract_value")),
        "contract_value": _money(record.get("contract_value") if record.get("contract_value") is not None else record.get("arr")),
        "health_indicators": health or ["unknown"],
        "risk_drivers": drivers or ["No active renewal risk drivers"],
        "mitigation_owner": _text(record.get("mitigation_owner") or record.get("owner") or "Unassigned"),
        "next_action": _text(record.get("next_action") or _next_action(severity)),
        "severity": severity,
    }


def _severity(days: int | None, health: list[str], incidents: list[str], blockers: list[str], record: dict[str, Any]) -> str:
    score = 0
    if days is not None:
        score += 35 if days <= 30 else 20 if days <= 90 else 5
    health_text = " ".join(health).lower()
    if any(word in health_text for word in ("red", "poor", "declining", "at risk", "low usage")):
        score += 30
    elif any(word in health_text for word in ("yellow", "watch", "mixed")):
        score += 15
    if incidents:
        score += 20
    if blockers:
        score += 20
    signal = _text(record.get("commercial_signal") or record.get("expansion_signal") or record.get("contraction_signal")).lower()
    if any(word in signal for word in ("contraction", "downsizing", "churn", "budget cut")):
        score += 25
    elif any(word in signal for word in ("expansion", "upsell", "growth")):
        score -= 10
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _risk_drivers(days: int | None, health: list[str], incidents: list[str], blockers: list[str], record: dict[str, Any]) -> list[str]:
    drivers: list[str] = []
    if days is not None and days <= 90:
        drivers.append("Renewal inside 90 days")
    if health and health != ["unknown"]:
        drivers.append(f"Health: {', '.join(health)}")
    if incidents:
        drivers.append(f"Open incidents: {len(incidents)}")
    if blockers:
        drivers.append(f"Open blockers: {len(blockers)}")
    signal = _text(record.get("commercial_signal") or record.get("expansion_signal") or record.get("contraction_signal"))
    if signal:
        drivers.append(f"Commercial signal: {signal}")
    return drivers


def _next_action(severity: str) -> str:
    return {
        "critical": "Run executive renewal save plan this week.",
        "high": "Assign mitigation owner and confirm customer recovery plan.",
        "medium": "Review health drivers in the next renewal checkpoint.",
        "low": "Maintain standard renewal monitoring.",
    }[severity]


def _date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({_text(item) for item in value if _text(item)})
    if isinstance(value, str):
        return sorted({item.strip() for item in value.replace(";", ",").split(",") if item.strip()})
    return []


def _money(value: Any) -> float:
    try:
        return round(float(str(value or 0).replace(",", "").replace("$", "")), 2)
    except ValueError:
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
