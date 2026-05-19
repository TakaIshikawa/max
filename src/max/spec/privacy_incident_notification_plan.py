"""Generate deterministic privacy incident notification plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.privacy_incident_notification_plan.v1"
PRIVACY_INCIDENT_NOTIFICATION_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.privacy_incident_notification_plan"


def generate_privacy_incident_notification_plan(spec_like: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic privacy incident notification planning data."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    ctx = context(spec)
    hints = _privacy_incident_hints(spec)
    evidence_ids = [item["id"] for item in ctx["evidence_references"]]
    strictness = "strict" if hints["regulated"] or hints["high_risk"] else ctx["strictness"]
    deadline = "72 hours from confirmation" if strictness == "strict" else "5 business days from confirmation"
    cadence = "twice daily until notifications are complete" if strictness == "strict" else "daily until closure"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            notification_strictness=strictness,
            incident_type=hints["incident_type"],
            regulated_regions=hints["regulated_regions"],
            notification_deadline=deadline,
            customer_communication_cadence=cadence,
        ),
        "notification_strategy": _notification_strategy(ctx, hints, strictness, deadline, evidence_ids),
        "affected_data_subjects": _affected_data_subjects(ctx, hints, evidence_ids),
        "regulatory_deadlines": _regulatory_deadlines(hints, strictness, evidence_ids),
        "customer_comms": _customer_comms(ctx, hints, strictness, cadence, evidence_ids),
        "evidence_preservation": _evidence_preservation(ctx, hints, strictness, evidence_ids),
        "owner_roles": _owner_roles(ctx),
        "evidence_references": ctx["evidence_references"],
    }


def _privacy_incident_hints(spec: dict[str, Any]) -> dict[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    incident = metadata.get("privacy_incident") if isinstance(metadata.get("privacy_incident"), dict) else {}
    execution = spec.get("execution") if isinstance(spec.get("execution"), dict) else {}
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    regions = _ordered(
        string_list(incident.get("regulatory_regions"))
        + string_list(metadata.get("regulatory_regions"))
        + string_list(metadata.get("regions"))
    )
    data_categories = _ordered(
        string_list(incident.get("data_categories"))
        + string_list(metadata.get("data_categories"))
        + string_list(project.get("data_categories"))
    )
    incident_subjects = _ordered(string_list(incident.get("affected_data_subjects")) + string_list(incident.get("data_subjects")))
    subjects = incident_subjects or _ordered(string_list(project.get("target_users")) + string_list(project.get("specific_user")))
    text = " ".join(
        string_list(execution.get("risks"))
        + string_list(metadata.get("risks"))
        + string_list(incident.get("risks"))
        + data_categories
        + regions
        + [
            compact(incident.get("severity")),
            compact(incident.get("impact")),
            compact(incident.get("type") or incident.get("incident_type")),
            compact(project.get("workflow_context")),
            compact(project.get("summary")),
        ]
    ).lower()
    regulated = bool(regions) or any(term in text for term in ("gdpr", "ccpa", "cpra", "hipaa", "dpa", "regulator", "supervisory authority"))
    high_risk = _truthy(incident.get("high_risk")) or any(
        term in text
        for term in (
            "breach",
            "exposure",
            "unauthorized",
            "personal data",
            "pii",
            "payment",
            "health",
            "credential",
            "data loss",
            "privacy",
        )
    )
    return {
        "incident_type": compact(incident.get("type") or incident.get("incident_type")) or ("regulated privacy incident" if regulated else "potential privacy incident"),
        "severity": compact(incident.get("severity")) or ("high" if high_risk else "medium"),
        "regulated_regions": regions or ["unconfirmed operating region"],
        "regulated": regulated,
        "high_risk": high_risk,
        "data_categories": data_categories or ["personal data potentially in scope"],
        "affected_subjects": subjects,
        "discovery_time": compact(incident.get("discovery_time") or incident.get("detected_at")) or "incident confirmation time",
        "systems": _ordered(string_list(incident.get("systems")) + string_list(metadata.get("systems")) + string_list(execution.get("mvp_scope"))),
    }


def _notification_strategy(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, deadline: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": "NS1",
        "name": "Privacy incident notification decision",
        "owner": "privacy_owner",
        "strictness": strictness,
        "incident_type": hints["incident_type"],
        "severity": hints["severity"],
        "decision_deadline": deadline,
        "strategy": f"Classify {ctx['workflow_context']} incident scope, legal notification triggers, and customer impact before notice approval.",
        "evidence_reference_ids": evidence_ids,
    }


def _affected_data_subjects(
    ctx: dict[str, Any], hints: dict[str, Any], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    subjects = hints["affected_subjects"] or [ctx["target_user"]]
    categories = ", ".join(hints["data_categories"])
    return [
        {
            "id": f"ADS{index}",
            "segment": subject,
            "data_categories": categories,
            "impact": "potential exposure or misuse risk" if hints["high_risk"] else "notification eligibility under review",
            "support_path": "privacy support queue with identity-safe incident handling",
            "evidence_reference_ids": evidence_ids,
        }
        for index, subject in enumerate(subjects, start=1)
    ]


def _regulatory_deadlines(
    hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    regions = hints["regulated_regions"]
    regulator_deadline = "72 hours from confirmation" if strictness == "strict" else "5 business days from confirmation"
    subject_deadline = "without undue delay after notice approval" if strictness == "strict" else "after legal review confirms notice is required"
    return [
        {
            "id": "RD1",
            "region": ", ".join(regions),
            "recipient": "privacy regulator or supervisory authority",
            "deadline": regulator_deadline,
            "owner": "legal_owner",
            "condition": "notify if reportability threshold is met for the affected region",
            "evidence_reference_ids": evidence_ids,
        },
        {
            "id": "RD2",
            "region": ", ".join(regions),
            "recipient": "affected data subjects",
            "deadline": subject_deadline,
            "owner": "privacy_owner",
            "condition": "notify impacted people when material privacy risk or legal trigger is confirmed",
            "evidence_reference_ids": evidence_ids,
        },
    ]


def _customer_comms(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, cadence: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    milestones = (
        [
            ("CC1", "within 24 hours", "prepare holding statement, support macros, and regulator-safe customer language"),
            ("CC2", "within 72 hours", "send required notices with known facts, actions taken, and customer protective steps"),
            ("CC3", cadence, "publish updates until containment, notification, and support follow-up are complete"),
        ]
        if strictness == "strict"
        else [
            ("CC1", "within 2 business days", "prepare customer-facing statement and support guidance"),
            ("CC2", cadence, "update impacted customers if scope, impact, or remediation materially changes"),
        ]
    )
    return [
        {
            "id": item_id,
            "milestone": milestone,
            "owner": "communications_owner" if item_id != "CC3" else "support_owner",
            "message": f"{message} for {ctx['title']}.",
            "channels": ["email", "support ticket", "status page"] if hints["high_risk"] else ["email", "support ticket"],
            "evidence_reference_ids": evidence_ids,
        }
        for item_id, milestone, message in milestones
    ]


def _evidence_preservation(
    ctx: dict[str, Any], hints: dict[str, Any], strictness: str, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    systems = ", ".join(hints["systems"] or ctx["mvp_scope"] or ["target systems"])
    retention = "legal hold until counsel releases incident evidence" if strictness == "strict" else "retain until incident closure and review"
    return [
        _preservation("EP1", "Incident timeline", "incident_commander", f"Record discovery, containment, assessment, notice decisions, and closeout timestamps from {hints['discovery_time']}.", retention, evidence_ids),
        _preservation("EP2", "Affected data inventory", "data_owner", f"Preserve extracts and access logs for {systems} covering affected data categories.", retention, evidence_ids),
        _preservation("EP3", "Notification approvals", "legal_owner", "Store legal analysis, regulator decisions, customer notice copy, and delivery proof.", retention, evidence_ids),
    ]


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"role": "incident_commander", "suggested_owner": "incident_commander", "responsibility": "Own incident timeline, severity, decision cadence, and cross-functional coordination."},
        {"role": "privacy_owner", "suggested_owner": ctx["buyer"], "responsibility": "Own data-subject impact assessment and privacy notification readiness."},
        {"role": "legal_owner", "suggested_owner": "legal_owner", "responsibility": "Determine reportability, regulatory deadlines, and approved notification language."},
        {"role": "communications_owner", "suggested_owner": "communications_owner", "responsibility": "Prepare customer notices, status updates, and support-approved messaging."},
        {"role": "data_owner", "suggested_owner": "data_owner", "responsibility": "Confirm affected systems, subjects, data categories, and preservation evidence."},
    ]


def _preservation(
    item_id: str, name: str, owner: str, description: str, retention: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "description": description,
        "retention": retention,
        "evidence_reference_ids": evidence_ids,
    }


def _ordered(values: list[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=str.casefold)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return compact(value).lower() in {"1", "true", "yes", "y", "required", "high"}
