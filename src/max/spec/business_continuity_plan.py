"""Generate deterministic business continuity plans."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.spec.business_continuity_plan.v1"
KIND = "max.spec.business_continuity_plan"


def generate_business_continuity_plan(continuity_context: dict[str, Any]) -> dict[str, Any]:
    """Return a stable business continuity plan from operational context."""
    ctx = _context(continuity_context)
    critical_customer = ctx["customer_facing"] or ctx["criticality"] == "critical"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "critical_functions": ctx["critical_functions"],
        "disruption_scenarios": ctx["disruption_scenarios"],
        "dependencies": ctx["dependencies"],
        "continuity_procedures": [
            "Declare continuity event and assign continuity lead.",
            "Prioritize critical functions and dependency workarounds.",
            "Run manual procedure until recovery owner confirms normal operations.",
        ],
        "staffing_assumptions": ctx["staffing"],
        "communication_channels": {
            "internal": ctx["internal_channel"],
            "customer": "customer status page and account team updates" if critical_customer else "support macros if needed",
            "executive": "hourly executive updates" if critical_customer else "daily summary",
        },
        "recovery_priorities": ctx["critical_functions"],
        "manual_workarounds": ctx["manual_workarounds"],
        "evidence": [
            "continuity declaration time and owner",
            "manual workaround log and customer-impact notes",
            "recovery validation and after-action items",
        ],
        "review_cadence": "semiannual" if critical_customer else "annual",
    }


def _context(value: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    functions = _list(raw.get("critical_functions")) or ["customer support", "incident response"]
    return {
        "criticality": (_text(raw.get("criticality")) or "standard").lower(),
        "customer_facing": bool(raw.get("customer_facing")),
        "critical_functions": functions,
        "disruption_scenarios": _list(raw.get("disruption_scenarios"))
        or ["office or workforce disruption", "critical SaaS dependency outage"],
        "dependencies": _list(raw.get("dependencies")) or ["identity provider", "support desk", "communications"],
        "staffing": _list(raw.get("staffing_assumptions"))
        or ["primary owner and backup owner available for each critical function"],
        "internal_channel": _text(raw.get("internal_channel")) or "continuity-bridge",
        "manual_workarounds": _list(raw.get("manual_workarounds"))
        or ["track requests in approved spreadsheet", "use phone bridge for priority decisions"],
    }


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""
