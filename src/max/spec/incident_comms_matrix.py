"""Generate deterministic incident communications matrices for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import CSV_COLUMNS as INCIDENT_COMMS_MATRIX_CSV_COLUMNS
from max.spec._planning_common import context, extend_section, markdown_header, render_csv, render_evidence, render_item, summary

SCHEMA_VERSION = "max-incident-comms-matrix/v1"
KIND = "max.incident_comms_matrix"
_SECTIONS = ("stakeholder_channels", "severity_notifications", "message_templates", "escalation_handoffs", "status_promises")


def generate_incident_comms_matrix(tact_spec: dict[str, Any]) -> dict[str, Any]:
    ctx = context(tact_spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, channel_count=4),
        "stakeholder_channels": [
            _item("CH1", "target_user_channel", "channel", f"Notify {ctx['target_user']} through support-owned status updates.", "support_owner", "high", "incident open", references=["project.specific_user"]),
            _item("CH2", "buyer_channel", "channel", f"Notify {ctx['buyer']} with impact, mitigation, and next update time.", "product_owner", "high", "severity high+", references=["project.buyer"]),
            _item("CH3", "workflow_owner_channel", "channel", f"Coordinate operational updates for {ctx['workflow_context']}.", "launch_owner", "medium", "severity medium+", references=["project.workflow_context"]),
            _item("CH4", "engineering_channel", "channel", "Route technical updates, owners, and rollback state to on-call.", "on_call_owner", "critical", "all severities", references=["solution.technical_approach"]),
        ],
        "severity_notifications": [
            _item("SEV1", "critical", "severity", "Notify on-call immediately, sponsor within 15 minutes, customers within 30 minutes if impact persists.", "incident_commander", "critical", "0-30 minutes", references=["stakeholder_channels"]),
            _item("SEV2", "high", "severity", "Notify on-call within 15 minutes and impacted stakeholders within one hour.", "incident_commander", "high", "15-60 minutes", references=["stakeholder_channels"]),
            _item("SEV3", "medium", "severity", "Notify workflow owners and support before the next business update.", "launch_owner", "medium", "same business day", references=["stakeholder_channels"]),
        ],
        "message_templates": [
            _item("MSG1", "initial_notice", "template", "State impact, affected workflow, mitigation owner, and next update time.", "support_owner", "required", "incident open", references=["project.workflow_context"]),
            _item("MSG2", "resolution_notice", "template", "State resolution, follow-up action, and where evidence will be recorded.", "product_owner", "required", "incident close", references=["evidence_references"]),
        ],
        "escalation_handoffs": [
            _item("ESC1", "support_to_on_call", "handoff", "Support escalates repeated user impact or unclear workaround to on-call.", "support_owner", "high", "on repeated report", references=["project.specific_user"]),
            _item("ESC2", "on_call_to_sponsor", "handoff", "On-call escalates budget exhaustion, data risk, or rollback recommendation to sponsor.", "on_call_owner", "critical", "severity critical", references=["execution.risks"]),
        ],
        "status_promises": [
            _item("STA1", "customer_update_cadence", "promise", "Publish customer-facing updates on a fixed cadence until stable.", "support_owner", "required", "30 minutes critical, hourly high", references=["severity_notifications"]),
            _item("STA2", "internal_review_cadence", "promise", "Record owner, mitigation, and next action after every incident review checkpoint.", "incident_commander", "required", "each checkpoint", references=["escalation_handoffs"]),
        ],
        "evidence_references": ctx["evidence_references"],
    }


def render_incident_comms_matrix_markdown(matrix: dict[str, Any]) -> str:
    lines = markdown_header(matrix if isinstance(matrix, dict) else {}, "Incident Communications Matrix")
    for title, key in (("Severity Notifications", "severity_notifications"), ("Stakeholder Channels", "stakeholder_channels"), ("Message Templates", "message_templates"), ("Escalation Handoffs", "escalation_handoffs"), ("Status Promises", "status_promises"), ("Evidence References", "evidence_references")):
        extend_section(lines, title, (matrix or {}).get(key) or [], render_evidence if key == "evidence_references" else render_item)
    return "\n".join(lines).rstrip() + "\n"


def render_incident_comms_matrix_csv(matrix: dict[str, Any]) -> str:
    return render_csv(matrix if isinstance(matrix, dict) else {}, _SECTIONS)


def _item(item_id: str, name: str, item_type: str, description: str, owner: str, severity: str, timing: str, *, references: list[str]) -> dict[str, Any]:
    return {"id": item_id, "name": name, "type": item_type, "description": description, "owner": owner, "severity": severity, "timing": timing, "references": references}
