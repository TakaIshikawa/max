"""Generate deterministic break-glass access plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.break_glass_access_plan.v1"
KIND = "max.spec.break_glass_access_plan"


def generate_break_glass_access_plan(spec_like: Any) -> dict[str, Any]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    systems = _values(hints.get("systems"), ["production environment"])
    roles = _values(hints.get("roles"), ["incident commander", "senior engineer"])
    approvers = _values(hints.get("approvers"), ["engineering_manager", "security_owner"])
    max_duration = compact(hints.get("max_duration")) or "2 hours"
    mfa_required = _truthy(hints.get("mfa_required"), default=True)
    ticket_required = _truthy(hints.get("ticket_required"), default=True)
    audit_log = compact(hints.get("audit_log")) or "central audit log"
    evidence_ids = _evidence_ids(ctx)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, systems=systems, max_duration=max_duration, mfa_required=mfa_required, ticket_required=ticket_required),
        "access_policy": [
            _item("AP1", "emergency_only", "security_owner", "Use break-glass access only for active incidents or urgent production recovery.", "high", evidence_ids=evidence_ids),
            _item("AP2", "maximum_duration", "security_owner", f"Access expires after {max_duration}.", "high", evidence_ids=evidence_ids),
        ],
        "eligible_roles": [_item(f"ER{index}", role, role, f"{role} may request break-glass access when policy conditions are met.", "high", evidence_ids=evidence_ids) for index, role in enumerate(roles, start=1)],
        "approval_flow": _approval_flow(approvers, mfa_required, ticket_required, evidence_ids),
        "activation_steps": [
            _item("AS1", "open_request", "requester", "Open or link an emergency access ticket before activation." if ticket_required else "Record emergency reason before activation.", "high", evidence_ids=evidence_ids),
            _item("AS2", "verify_identity", "security_owner", "Verify requester identity with MFA before granting access." if mfa_required else "Verify requester identity before granting access.", "high", evidence_ids=evidence_ids),
            _item("AS3", "grant_scoped_access", "platform_owner", f"Grant least-privilege access only to {', '.join(systems)}.", "high", evidence_ids=evidence_ids),
        ],
        "monitoring_requirements": [
            _item("MR1", "live_session_monitoring", "security_owner", "Monitor privileged actions during the break-glass session.", "high", evidence_ids=evidence_ids),
            _item("MR2", "audit_log_capture", "security_owner", f"Capture commands, console actions, and identity events in {audit_log}.", "high", evidence_ids=evidence_ids),
        ],
        "revocation_steps": [
            _item("RS1", "time_boxed_revocation", "platform_owner", f"Automatically revoke access at {max_duration}.", "high", evidence_ids=evidence_ids),
            _item("RS2", "post_incident_cleanup", "platform_owner", "Remove temporary credentials, sessions, and group memberships immediately after use.", "high", evidence_ids=evidence_ids),
        ],
        "audit_requirements": [
            _item("AU1", "post_access_review", "security_owner", "Review access reason, approvers, actions taken, and revocation evidence within one business day.", "high", evidence_ids=evidence_ids),
            _item("AU2", "evidence_package", "compliance_owner", "Attach ticket, approvals, MFA proof, logs, and revocation proof to the evidence package.", "high", evidence_ids=evidence_ids),
        ],
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _approval_flow(approvers: list[str], mfa_required: bool, ticket_required: bool, evidence_ids: list[str]) -> list[dict[str, Any]]:
    rows = [_item(f"AF{index}", approver, approver, f"{approver} approves emergency access before activation.", "high", evidence_ids=evidence_ids) for index, approver in enumerate(approvers, start=1)]
    rows.append(_item(f"AF{len(rows) + 1}", "ticket_gate", "requester", "Ticket is mandatory before approval." if ticket_required else "Emergency reason is recorded for approval.", "high", evidence_ids=evidence_ids))
    rows.append(_item(f"AF{len(rows) + 1}", "mfa_gate", "security_owner", "MFA verification is mandatory before access is granted." if mfa_required else "Identity verification is mandatory before access is granted.", "high", evidence_ids=evidence_ids))
    return rows


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "security_owner", "suggested_owner": "security_owner", "responsibility": "Own policy, approval controls, monitoring, and post-access review."},
        {"role": "platform_owner", "suggested_owner": "platform_owner", "responsibility": "Grant scoped access and complete revocation."},
        {"role": "requester", "suggested_owner": "incident_responder", "responsibility": "Provide ticket, reason, and post-use summary."},
        {"role": "compliance_owner", "suggested_owner": ctx["buyer"], "responsibility": "Maintain break-glass audit evidence."},
    ]


def _hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    hints = metadata.get("break_glass")
    return hints if isinstance(hints, dict) else {}


def _values(value: Any, fallback: list[str]) -> list[str]:
    values = string_list(value)
    return sorted(dict.fromkeys(values), key=str.casefold) if values else fallback


def _truthy(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return compact(value).lower() in {"1", "true", "yes", "y", "required"}


def _item(item_id: str, name: str, owner: str, description: str, severity: str, *, evidence_ids: list[str] | None = None) -> dict[str, Any]:
    return {"id": item_id, "name": name, "owner": owner, "severity": severity, "description": description, "evidence_reference_ids": evidence_ids or []}


def _evidence_ids(ctx: dict[str, Any]) -> list[str]:
    return [item["id"] for item in ctx["evidence_references"]]
