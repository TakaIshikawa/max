"""Partner integration risk register export."""

from __future__ import annotations

import json
from typing import Any

SCHEMA_VERSION = "max.partner_integration_risk_register.v1"
KIND = "max.partner_integration_risk_register"
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def export_partner_integration_risk_register(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [_row(record) for record in records]
    rows.sort(key=lambda row: (_SEVERITY_ORDER[row["severity"]], -row["customer_exposure"], row["partner"].lower(), row["integration_area"].lower()))
    return rows


def render_partner_integration_risk_register_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def _row(record: dict[str, Any]) -> dict[str, Any]:
    drivers = _drivers(record)
    severity = _severity(record, drivers)
    return {
        "partner": _text(record.get("partner") or record.get("partner_name") or "Unknown"),
        "integration_area": _text(record.get("integration_area") or record.get("area") or "Unknown"),
        "customer_exposure": _exposure(record.get("customer_exposure") or record.get("customers") or record.get("affected_customers")),
        "risk_drivers": drivers or ["No active partner integration risk drivers"],
        "mitigation_owner": _text(record.get("mitigation_owner") or record.get("owner") or "Unassigned"),
        "severity": severity,
        "next_action": _text(record.get("next_action") or _next_action(severity)),
        "evidence": _items(record.get("evidence") or record.get("evidence_ids")),
    }


def _severity(record: dict[str, Any], drivers: list[str]) -> str:
    score = min(_exposure(record.get("customer_exposure") or record.get("customers") or record.get("affected_customers")) * 5, 35)
    text = " ".join(str(record.get(key, "")) for key in ("dependency_health", "api_risk", "contract_risk", "status")).lower()
    if any(word in text for word in ("down", "blocked", "breach", "critical", "expired")):
        score += 45
    elif any(word in text for word in ("degraded", "unstable", "renewal", "manual")):
        score += 25
    score += min(len(drivers) * 10, 30)
    if score >= 80:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _drivers(record: dict[str, Any]) -> list[str]:
    drivers = _items(record.get("risk_drivers"))
    for key, label in (("dependency_health", "Dependency health"), ("api_risk", "API risk"), ("contract_risk", "Contract risk")):
        value = _text(record.get(key))
        if value:
            drivers.append(f"{label}: {value}")
    return sorted(dict.fromkeys(drivers))


def _next_action(severity: str) -> str:
    return {
        "critical": "Escalate partner remediation and notify exposed account owners.",
        "high": "Confirm mitigation plan with partner owner this week.",
        "medium": "Track risk in the next integration review.",
        "low": "Maintain standard partner monitoring.",
    }[severity]


def _exposure(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    try:
        return max(int(float(str(value or 0).replace(",", ""))), 0)
    except ValueError:
        return 0


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({_text(item) for item in value if _text(item)})
    if isinstance(value, str):
        return sorted({item.strip() for item in value.replace(";", ",").split(",") if item.strip()})
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
