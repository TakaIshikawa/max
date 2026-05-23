"""Generate deterministic incident postmortem action verification plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.incident_postmortem_action_verification_plan.v1"
KIND = "max.spec.incident_postmortem_action_verification_plan"


def generate_incident_postmortem_action_verification_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "incident_postmortem_action_verification")
    actions = unique_records(
        named(hints.get("action_items") or hints.get("actions") or hints.get("postmortem_actions"), ("action", "title", "owner")),
        [{"name": "verify postmortem corrective action", "owner": "incident_owner", "severity": "high", "deadline": "next review"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, action_item_count=len(actions)),
        "action_items": [item("IPA", index, record, "incident_owner", evidence_ids, "Verify incident postmortem action", name_keys=("name", "action", "title"), extra_keys=("due_date", "deadline", "status", "incident_id")) for index, record in enumerate(actions, start=1)],
        "verification_steps": section(hints, ("verification_steps", "verification", "evidence"), "IPV", "incident_owner", "Collect verification evidence", evidence_ids, ["evidence of completed remediation and operational validation"]),
        "residual_risk_review": section(hints, ("residual_risk", "residual_risk_review"), "IPR", "risk_owner", "Review residual risk", evidence_ids, ["residual risk rating and acceptance owner"]),
        "sign_off": section(hints, ("sign_off", "signoff", "approvals"), "IPS", "stakeholder_owner", "Capture stakeholder sign-off", evidence_ids, ["incident commander, service owner, and security sign-off"]),
        "escalation_workflow": section(hints, ("escalation_workflow", "escalation", "overdue_escalation"), "IPE", "incident_owner", "Escalate overdue action", evidence_ids, ["overdue action escalation to service leadership"]),
        "evidence_references": ctx["evidence_references"],
    }
