"""Generate deterministic incident communications matrices for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_incident_markdown, summary

INCIDENT_COMMS_MATRIX_SCHEMA_VERSION = "max-incident-comms-matrix/v1"
KIND = "max.incident_comms_matrix"
INCIDENT_COMMS_MATRIX_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = (
    "stakeholder_channels",
    "severity_notifications",
    "message_templates",
    "escalation_handoffs",
    "status_promises",
)


def generate_incident_comms_matrix(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec preview into communication ownership and timing guidance."""
    context = base_context(tact_spec)
    stakeholder_channels = [
        item("SC1", "buyer_updates", f"Keep {context['buyer']} current on launch-impacting incidents.", "incident_commander", stakeholder=context["buyer"], timing="initial update within 15 minutes", evidence=["project.buyer"]),
        item("SC2", "user_updates", f"Notify {context['target_user']} about degraded {context['workflow']} behavior.", "customer_success_owner", stakeholder=context["target_user"], timing="initial update within 30 minutes", evidence=["project.target_users", "project.workflow_context"]),
        item("SC3", "support_updates", f"Route support talking points through {context['support_context']}.", "support_owner", stakeholder="support team", timing="before customer-facing reply", evidence=["execution.support_context"]),
        item("SC4", "engineering_updates", f"Coordinate technical facts for {context['technical_approach']}.", "engineering_owner", stakeholder="engineering on-call", timing="continuous during active incident", evidence=["solution.technical_approach"]),
    ]
    severity_notifications = [
        item("SN1", "sev1_customer_impact", f"Material outage or data-risk event affecting {context['workflow']}.", "incident_commander", severity="sev1", stakeholder=context["buyer"], timing="15 minutes", action="Open executive, support, and status-page channels.", evidence=["execution.risks"]),
        item("SN2", "sev2_workflow_degradation", f"Partial degradation for {context['target_user']} with workaround available.", "support_owner", severity="sev2", stakeholder=context["target_user"], timing="30 minutes", action="Publish workaround and next-update time.", evidence=["project.specific_user"]),
        item("SN3", "sev3_internal_watch", "Contained defect, dependency delay, or low-volume support signal.", "engineering_owner", severity="sev3", stakeholder="internal launch team", timing="next business update", action="Track in launch notes and escalate if impact grows.", evidence=["execution.validation_plan"]),
    ]
    message_templates = [
        item("MT1", "initial_acknowledgement", f"We are investigating impact to {context['workflow']} and will share the next update on schedule.", "support_owner", timing="first response", evidence=["project.workflow_context"]),
        item("MT2", "workaround_update", f"{context['target_user']} can use the documented fallback while the team restores normal behavior.", "customer_success_owner", timing="during mitigation", evidence=["project.target_users"]),
        item("MT3", "resolution_notice", "Incident is resolved after monitoring confirms stable operation and support receives closure notes.", "incident_commander", timing="after recovery validation", evidence=["execution.validation_plan"]),
    ]
    escalation_handoffs = [
        item("EH1", "support_to_incident_command", "Support escalates repeated customer-impacting reports with examples and timestamps.", "support_owner", timing="2 matching reports or any sev1 report", action="Assign incident_commander and open comms log.", evidence=["support_context"]),
        item("EH2", "engineering_to_customer_owner", "Engineering hands confirmed customer impact, workaround, and ETA to customer-facing owners.", "engineering_owner", timing="after diagnosis", action="Update templates and affected-stakeholder list.", evidence=["solution.technical_approach"]),
        item("EH3", "incident_command_to_buyer", f"Incident commander escalates business impact and promise changes to {context['buyer']}.", "incident_commander", timing="promise at risk", action="Record decision and next update cadence.", evidence=["project.buyer"]),
    ]
    status_promises = [
        item("SP1", "sev1_status_promise", "Public or buyer-facing status is updated every 30 minutes until impact is mitigated.", "incident_commander", severity="sev1", timing="every 30 minutes", evidence=["severity_notifications"]),
        item("SP2", "sev2_status_promise", "Affected users receive workaround and progress updates every 2 hours during staffed coverage.", "support_owner", severity="sev2", timing="every 2 hours", evidence=["stakeholder_channels"]),
        item("SP3", "sev3_status_promise", "Internal launch notes capture diagnosis, owner, and next review date.", "engineering_owner", severity="sev3", timing="next launch review", evidence=["execution.validation_plan"]),
    ]
    return {
        "schema_version": INCIDENT_COMMS_MATRIX_SCHEMA_VERSION,
        "kind": KIND,
        "source": context["source"],
        "summary": summary(context, stakeholder_channel_count=len(stakeholder_channels)),
        "stakeholder_channels": stakeholder_channels,
        "severity_notifications": severity_notifications,
        "message_templates": message_templates,
        "escalation_handoffs": escalation_handoffs,
        "status_promises": status_promises,
        "evidence_references": context["evidence_references"],
    }


def render_incident_comms_matrix_markdown(matrix: dict[str, Any]) -> str:
    return render_incident_markdown(matrix)


def render_incident_comms_matrix_csv(matrix: dict[str, Any]) -> str:
    return render_csv(matrix, SECTIONS)
