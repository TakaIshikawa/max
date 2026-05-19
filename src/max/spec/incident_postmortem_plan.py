"""Generate deterministic incident postmortem plans for TactSpec previews."""

from __future__ import annotations

from typing import Any, Mapping

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

INCIDENT_POSTMORTEM_PLAN_SCHEMA_VERSION = "max-incident-postmortem-plan/v1"
KIND = "max.incident_postmortem_plan"
INCIDENT_POSTMORTEM_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("incident_timeline", "customer_impact", "detection_response", "contributing_factors", "corrective_actions", "owners_deadlines", "follow_up_checks", "publication_readiness", "evidence")


def generate_incident_postmortem_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    incident = _mapping(context["spec"].get("incident") or context["spec"].get("postmortem"))
    severity = (_text(incident.get("severity")) or "sev3").lower()
    urgency = "24 hours" if severity in {"sev0", "sev1"} else "3 business days" if severity == "sev2" else "5 business days"
    incident_id = _text(incident.get("incident_id")) or context["source"].get("idea_id") or "incident"

    return {
        "schema_version": INCIDENT_POSTMORTEM_PLAN_SCHEMA_VERSION,
        "kind": KIND,
        "source": context["source"],
        "summary": summary(context, incident_id=incident_id, severity=severity, review_urgency=urgency),
        "incident_timeline": [
            item("TL1", "timeline_capture", "Capture detection, declaration, mitigation, resolution, and customer notification timestamps.", "incident_commander", timing=urgency, evidence=["incident.timeline"])
        ],
        "customer_impact": [
            item("IMP1", "impact_summary", f"Summarize customer impact for {context['target_user']} and affected workflows.", "product_owner", severity="high" if severity in {"sev0", "sev1"} else "medium", evidence=["incident.impact"])
        ],
        "detection_response": [
            item("DET1", "detection_and_response", "Document detection signal, alert owner, escalation path, and response decisions.", "on_call_owner", evidence=["incident.detection"])
        ],
        "contributing_factors": [
            item("FAC1", "factor_analysis", "List technical, process, monitoring, and communication factors without assigning blame.", "engineering_owner", evidence=["incident.contributing_factors"])
        ],
        "corrective_actions": [
            item("ACT1", "prevent_recurrence", "Create corrective actions for prevention, detection, mitigation, and customer communication gaps.", "engineering_owner", action="Each action needs owner and deadline.", evidence=["execution.risks"])
        ],
        "owners_deadlines": [
            item("OWN1", "action_owners", f"Assign owners and deadlines; {severity.upper()} review is due within {urgency}.", "incident_commander", timing=urgency, evidence=["incident.owners"])
        ],
        "follow_up_checks": [
            item("FUP1", "verification_check", "Schedule follow-up checks for completed actions and reopened risks.", "release_manager", timing="next review cycle", evidence=["execution.validation_plan"])
        ],
        "publication_readiness": [
            item("PUB1", "publish_review", "Review customer-safe summary, internal details, and leadership approval before publication.", "communications_owner", action="Publish only after impact and actions are approved.", evidence=["project.support_context"])
        ],
        "evidence": [
            item("EV1", "postmortem_evidence", "Attach timeline, impact data, alert history, chat transcript, corrective action tracker, and publication record.", "incident_commander", action="Required for closure.", evidence=["evidence.references"])
        ],
        "evidence_references": context["evidence_references"],
    }


def render_incident_postmortem_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "Incident Postmortem Plan", SECTIONS)


def render_incident_postmortem_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
