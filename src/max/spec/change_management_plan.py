"""Generate deterministic change management plans."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.spec.change_management_plan.v1"
KIND = "max.spec.change_management_plan"


def generate_change_management_plan(change_context: dict[str, Any]) -> dict[str, Any]:
    """Return a stable operational change plan from structured context."""
    ctx = _context(change_context)
    high_risk = ctx["risk_level"] in {"high", "critical"} or ctx["environment"] == "production"
    approvals = [
        {"approval": "change_owner", "owner": ctx["change_owner"], "required": True},
        {"approval": "service_owner", "owner": ctx["service_owner"], "required": True},
        {"approval": "security_or_compliance", "owner": ctx["risk_owner"], "required": high_risk},
    ]
    rollback = [
        "Stop rollout and freeze additional changes.",
        "Restore previous version or configuration from the approved artifact.",
        "Run validation checks and notify stakeholders of rollback status.",
    ]
    if high_risk:
        rollback.append("Escalate rollback decision to incident commander when customer impact is detected.")

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "change_summary": ctx["summary"],
        "environment": ctx["environment"],
        "impacted_systems": ctx["impacted_systems"],
        "risk_level": ctx["risk_level"],
        "approvals": approvals,
        "rollout_steps": ctx["rollout_steps"],
        "validation": ctx["validation"],
        "rollback": rollback,
        "communication_plan": {
            "audiences": ctx["audiences"],
            "timing": "before, during, and after change window" if high_risk else "before and after change",
            "channel": ctx["channel"],
        },
        "blackout_windows": ctx["blackout_windows"],
        "post_change_evidence": [
            "deployment or change ticket link",
            "validation results and monitoring snapshot",
            "approval history and rollback decision record",
        ],
    }


def _context(value: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    risk = (_text(raw.get("risk_level")) or "low").lower()
    environment = (_text(raw.get("environment")) or "staging").lower()
    return {
        "summary": _text(raw.get("change_summary") or raw.get("summary"))
        or "Apply approved product or infrastructure change.",
        "environment": environment,
        "impacted_systems": _list(raw.get("impacted_systems")) or ["primary service"],
        "risk_level": risk,
        "change_owner": _text(raw.get("change_owner")) or "Change owner",
        "service_owner": _text(raw.get("service_owner")) or "Service owner",
        "risk_owner": _text(raw.get("risk_owner")) or "Security owner",
        "rollout_steps": _list(raw.get("rollout_steps"))
        or ["Open change window.", "Deploy change to target environment.", "Monitor service health."],
        "validation": _list(raw.get("validation"))
        or ["Confirm health checks pass.", "Review error rate and latency.", "Verify core user workflow."],
        "audiences": _list(raw.get("audiences")) or ["service team", "support team"],
        "channel": _text(raw.get("channel")) or "change-management channel",
        "blackout_windows": _list(raw.get("blackout_windows")) or ["customer peak usage periods"],
    }


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""
