"""Generate deterministic business continuity plans."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.spec.business_continuity_plan.v1"
KIND = "max.spec.business_continuity_plan"


def generate_business_continuity_plan(continuity_context: dict[str, Any]) -> dict[str, Any]:
    """Return a stable business continuity plan from operational context."""
    ctx = _context(continuity_context)
    critical_customer = ctx["customer_facing"] or ctx["criticality"] == "critical"
    escalation = "escalated" if critical_customer else "standard"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "critical_functions": ctx["critical_functions"],
        "disruption_scenarios": ctx["disruption_scenarios"],
        "dependencies": ctx["dependencies"],
        "continuity_procedures": [
            {
                "step": "Declare continuity event",
                "owner": ctx["continuity_lead"],
                "action": "Open the continuity bridge, record start time, and assign functional owners.",
            },
            {
                "step": "Prioritize critical functions",
                "owner": ctx["operations_owner"],
                "action": "Sequence recovery by customer impact, revenue impact, and regulatory obligation.",
            },
            {
                "step": "Activate dependency workarounds",
                "owner": ctx["dependency_owner"],
                "action": "Switch to approved alternate tools or manual queues until normal service is validated.",
            },
            {
                "step": "Validate return to normal operations",
                "owner": ctx["recovery_owner"],
                "action": "Confirm backlog, data integrity, and stakeholder sign-off before closing the event.",
            },
        ],
        "staffing_assumptions": ctx["staffing"],
        "communication_channels": {
            "level": escalation,
            "internal": ctx["internal_channel"],
            "customer": "customer status page and account team updates" if critical_customer else "support macros if needed",
            "executive": "hourly executive updates" if critical_customer else "daily summary",
        },
        "recovery_priorities": [
            {"rank": index + 1, "function": function, "target": _recovery_target(index, critical_customer)}
            for index, function in enumerate(ctx["critical_functions"])
        ],
        "manual_workarounds": ctx["manual_workarounds"],
        "evidence": [
            "continuity declaration time and owner",
            "manual workaround log and customer-impact notes",
            "dependency status snapshots and recovery decisions",
            "staffing roster with primary and backup coverage",
            "communication drafts, approvals, and sent timestamps",
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
        "continuity_lead": _text(raw.get("continuity_lead")) or "Continuity lead",
        "operations_owner": _text(raw.get("operations_owner")) or "Operations owner",
        "dependency_owner": _text(raw.get("dependency_owner")) or "Dependency owner",
        "recovery_owner": _text(raw.get("recovery_owner")) or "Recovery owner",
    }


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""


def _recovery_target(index: int, critical_customer: bool) -> str:
    targets = ["0-2 hours", "same business day", "next business day"]
    if critical_customer:
        targets = ["0-1 hour", "0-4 hours", "same business day"]
    return targets[min(index, len(targets) - 1)]
