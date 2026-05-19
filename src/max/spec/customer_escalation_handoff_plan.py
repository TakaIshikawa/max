"""Generate deterministic customer escalation handoff plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.customer_escalation_handoff_plan.v1"
KIND = "max.spec.customer_escalation_handoff_plan"


def generate_customer_escalation_handoff_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    customer = compact(hints.get("customer")) or "customer account"
    severity = _severity(hints.get("severity"), ctx)
    high = severity in {"sev1", "critical", "high"}
    issues = _values(hints.get("issues"), ["open customer escalation"])
    owners = _values(hints.get("owners"), ["support_owner", "delivery_owner"])
    exec_owner = compact(hints.get("executive_owner")) or ("executive_sponsor" if high else "")
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, customer=customer, severity=severity, high_severity=high),
        "escalation_summary": [_item("ES1", "handoff_scope", "support_owner", f"Hand off {severity} escalation for {customer}.", "high" if high else "medium", evidence_ids=evidence_ids)],
        "customer_context": [
            _item("CC1", "customer", "account_owner", f"Customer context: {customer}.", "medium", evidence_ids=evidence_ids),
            _item("CC2", "business_context", "account_owner", compact(hints.get("business_context")) or f"Escalation affects {ctx['workflow_context']}.", "high" if high else "medium", evidence_ids=evidence_ids),
        ],
        "severity_assessment": [_item("SA1", severity, "support_owner", "Treat as executive-visible escalation." if high else "Track as standard customer escalation.", "critical" if severity in {"sev1", "critical"} else ("high" if high else "medium"), evidence_ids=evidence_ids)],
        "owner_assignments": _owner_assignments(owners, exec_owner, high, evidence_ids),
        "response_timeline": [
            _item("RT1", "acknowledgement", "support_owner", "Acknowledge handoff within 15 minutes." if high else "Acknowledge handoff within 4 business hours.", "high" if high else "medium", timing="15 minutes" if high else "4 business hours", evidence_ids=evidence_ids),
            _item("RT2", "next_update", "communications_owner", "Send hourly updates until stabilized." if high else "Send daily updates until resolved.", "high" if high else "medium", timing="hourly" if high else "daily", evidence_ids=evidence_ids),
        ],
        "resolution_workstreams": [_item(f"RW{index}", issue, "delivery_owner", f"Drive resolution workstream for {issue}.", "high" if high else "medium", evidence_ids=evidence_ids) for index, issue in enumerate(issues, start=1)],
        "communication_plan": [
            _item("CP1", "customer_update", "communications_owner", "Provide executive-ready customer updates." if high else "Provide clear customer status updates.", "high" if high else "medium", evidence_ids=evidence_ids),
            _item("CP2", "internal_sync", "support_owner", "Run live internal escalation bridge." if high else "Run scheduled internal owner sync.", "high" if high else "medium", evidence_ids=evidence_ids),
        ],
        "owner_roles": _owner_roles(ctx, exec_owner),
        "evidence_references": ctx["evidence_references"],
    }


def _owner_assignments(owners: list[str], exec_owner: str, high: bool, evidence_ids: list[str]) -> list[dict[str, Any]]:
    assignments = [_item(f"OA{index}", owner, owner, f"{owner} owns escalation handoff actions.", "high" if high else "medium", evidence_ids=evidence_ids) for index, owner in enumerate(owners, start=1)]
    if exec_owner:
        assignments.append(_item(f"OA{len(assignments) + 1}", "executive_owner", exec_owner, f"{exec_owner} owns executive sponsor coverage.", "high" if high else "medium", evidence_ids=evidence_ids))
    return assignments


def _owner_roles(ctx: dict[str, Any], exec_owner: str) -> list[dict[str, str]]:
    return [
        {"role": "support_owner", "suggested_owner": "support_owner", "responsibility": "Own intake, acknowledgement, status cadence, and support actions."},
        {"role": "delivery_owner", "suggested_owner": "delivery_owner", "responsibility": "Own resolution workstreams and dependency follow-up."},
        {"role": "account_owner", "suggested_owner": ctx["buyer"], "responsibility": "Maintain customer context and commercial risk view."},
        {"role": "executive_owner", "suggested_owner": exec_owner or "not_required", "responsibility": "Provide executive sponsor coverage for high-severity escalations."},
    ]


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("customer_escalation_handoff")
    return hints if isinstance(hints, dict) else {}


def _severity(value: Any, ctx: dict[str, Any]) -> str:
    severity = compact(value).lower()
    return severity or ("high" if ctx["strictness"] == "strict" else "medium")


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _item(item_id: str, name: str, owner: str, description: str, severity: str, *, timing: str = "planned", evidence_ids: list[str] | None = None) -> dict[str, Any]:
    return {"id": item_id, "name": name, "owner": owner, "severity": severity, "timing": timing, "description": description, "evidence_reference_ids": evidence_ids or []}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
