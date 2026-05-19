"""Generate deterministic on-call handoff plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.on_call_handoff_plan.v1"
KIND = "max.spec.on_call_handoff_plan"


def generate_on_call_handoff_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    services = _values(hints.get("services"), ["primary service"])
    current_owner = compact(hints.get("current_owner")) or "current_on_call"
    next_owner = compact(hints.get("next_owner")) or "next_on_call"
    escalation_policy = compact(hints.get("escalation_policy")) or "standard escalation policy"
    issues = _values(hints.get("known_issues"), [])
    dashboards = _values(hints.get("dashboards"), ["service health dashboard"])
    alerts = _values(hints.get("alerts"), ["critical service alerts"])
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, service_count=len(services), current_owner=current_owner, next_owner=next_owner, escalation_policy=escalation_policy),
        "handoff_summary": [
            _item("HS1", "ownership_transition", current_owner, f"Transfer on-call ownership from {current_owner} to {next_owner}.", "medium", evidence_ids=evidence_ids),
            _item("HS2", "escalation_policy", next_owner, f"Use {escalation_policy} for urgent escalation.", "medium", evidence_ids=evidence_ids),
        ],
        "service_coverage": [_item(f"SC{index}", service, next_owner, f"{next_owner} covers {service} during the handoff window.", "medium", evidence_ids=evidence_ids) for index, service in enumerate(services, start=1)],
        "active_risks": _active_risks(issues, alerts, next_owner, evidence_ids),
        "escalation_paths": [
            _item("EP1", "primary_escalation", next_owner, f"Escalate through {escalation_policy}.", "high" if issues else "medium", evidence_ids=evidence_ids),
            _item("EP2", "secondary_owner", "incident_commander", "Page incident commander if owner acknowledgement misses the policy target.", "high" if issues else "medium", evidence_ids=evidence_ids),
        ],
        "runbook_checklist": _runbook_checklist(dashboards, alerts, next_owner, evidence_ids),
        "shift_transition_steps": [
            _item("ST1", "review_open_incidents", current_owner, "Review open incidents, recent deploys, and suppressed alerts.", "medium", evidence_ids=evidence_ids),
            _item("ST2", "confirm_receipt", next_owner, "Confirm ownership, paging reachability, dashboards, and escalation path.", "medium", evidence_ids=evidence_ids),
            _item("ST3", "record_handoff", next_owner, "Record handoff completion and unresolved risks.", "medium", evidence_ids=evidence_ids),
        ],
        "owner_roles": _owner_roles(current_owner, next_owner),
        "evidence_references": ctx["evidence_references"],
    }


def _active_risks(issues: list[str], alerts: list[str], owner: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    risks = [_item(f"AR{index}", issue, owner, f"Track known issue: {issue}.", "high", evidence_ids=evidence_ids) for index, issue in enumerate(issues, start=1)]
    if not risks:
        risks.append(_item("AR1", "no_known_issues", owner, "No known issues provided; verify recent incidents and alert history.", "medium", evidence_ids=evidence_ids))
    risks.append(_item(f"AR{len(risks) + 1}", "alert_watch", owner, f"Watch active alerts: {', '.join(alerts)}.", "medium", evidence_ids=evidence_ids))
    return risks


def _runbook_checklist(dashboards: list[str], alerts: list[str], owner: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    rows = [_item(f"RB{index}", dashboard, owner, f"Open and verify dashboard: {dashboard}.", "medium", evidence_ids=evidence_ids) for index, dashboard in enumerate(dashboards, start=1)]
    offset = len(rows)
    rows.extend(_item(f"RB{offset + index}", alert, owner, f"Confirm alert routing and current status for {alert}.", "medium", evidence_ids=evidence_ids) for index, alert in enumerate(alerts, start=1))
    return rows


def _owner_roles(current_owner: str, next_owner: str) -> list[dict[str, str]]:
    return [
        {"role": "current_on_call", "suggested_owner": current_owner, "responsibility": "Provide active context, open risks, and recent operational history."},
        {"role": "next_on_call", "suggested_owner": next_owner, "responsibility": "Accept paging ownership and monitor covered services."},
        {"role": "incident_commander", "suggested_owner": "incident_commander", "responsibility": "Provide escalation support when handoff risks become incidents."},
    ]


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("on_call_handoff")
    return hints if isinstance(hints, dict) else {}


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _item(item_id: str, name: str, owner: str, description: str, severity: str, *, evidence_ids: list[str] | None = None) -> dict[str, Any]:
    return {"id": item_id, "name": name, "owner": owner, "severity": severity, "description": description, "evidence_reference_ids": evidence_ids or []}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
