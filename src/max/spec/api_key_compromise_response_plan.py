"""Generate deterministic API key compromise response plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.api_key_compromise_response_plan.v1"
KIND = "max.spec.api_key_compromise_response_plan"


def generate_api_key_compromise_response_plan(
    spec_like: Any | None = None,
    *,
    compromised_key_ids: list[str] | None = None,
    services: list[str] | None = None,
    detection_source: str | None = None,
    containment_deadline: str | None = None,
    approvers: list[str] | None = None,
) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like or {}, "api_key_compromise_response")
    key_ids = compromised_key_ids or _strings(hints.get("compromised_key_ids") or hints.get("keys"), ["unknown-key"])
    service_names = services or _strings(hints.get("services"), ["affected-service"])
    deadline = compact(containment_deadline or hints.get("containment_deadline")) or "immediate"
    approver_names = approvers or _strings(hints.get("approvers"), ["security_approver"])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": "API Key Compromise Response Plan",
        "source": ctx["source"],
        "scope": {
            "compromised_key_ids": key_ids,
            "services": service_names,
            "detection_source": compact(detection_source or hints.get("detection_source")) or "unconfirmed detection source",
            "containment_deadline": deadline,
        },
        "summary": source_summary(ctx, compromised_key_count=len(key_ids), service_count=len(service_names)),
        "sections": [
            {
                "id": "affected_credentials",
                "title": "Affected Credentials",
                "owner": "security_owner",
                "items": [_credential(index, key_id, service_names, evidence_ids) for index, key_id in enumerate(key_ids, start=1)],
            },
            {
                "id": "containment_actions",
                "title": "Containment Actions",
                "owner": "incident_commander",
                "items": section(hints, ("containment_actions", "containment"), "AKC", "incident_commander", "Contain API key compromise", evidence_ids, [f"Revoke or disable affected keys by {deadline}"]),
            },
            {
                "id": "customer_impact",
                "title": "Customer Impact",
                "owner": "customer_owner",
                "items": section(hints, ("customer_impact", "impact"), "AKI", "customer_owner", "Assess customer impact", evidence_ids, ["Identify affected tenants, request classes, and notification requirements"]),
            },
            {
                "id": "evidence_preservation",
                "title": "Evidence Preservation",
                "owner": "security_owner",
                "items": section(hints, ("evidence_preservation", "evidence"), "AKE", "security_owner", "Preserve incident evidence", evidence_ids, ["Preserve audit logs, access logs, alert context, and investigation notes"]),
            },
            {
                "id": "rotation_validation",
                "title": "Rotation Validation",
                "owner": "platform_owner",
                "items": section(hints, ("rotation_validation", "validation_steps"), "AKV", "platform_owner", "Validate credential rotation", evidence_ids, ["Confirm replacement keys are scoped, deployed, and old keys cannot authenticate"]),
            },
            {
                "id": "monitoring",
                "title": "Monitoring",
                "owner": "security_owner",
                "items": section(hints, ("monitoring", "monitors"), "AKM", "security_owner", "Monitor for continued abuse", evidence_ids, ["Add temporary alerts for attempted use of revoked credentials and anomalous API traffic"]),
            },
            {
                "id": "post_incident_follow_up",
                "title": "Post-Incident Follow-Up",
                "owner": "incident_commander",
                "items": section(hints, ("post_incident_follow_up", "follow_up"), "AKF", "incident_commander", "Complete post-incident follow-up", evidence_ids, ["Document root cause, control gaps, owners, due dates, and prevention work"]),
            },
        ],
        "owners": {"incident_commander": "incident_commander", "security_owner": "security_owner", "platform_owner": "platform_owner"},
        "validation_steps": ["revoked_key_authentication_fails", "replacement_key_deployed", "monitoring_alerts_enabled"],
        "approvers": approver_names,
        "evidence_links": ctx["evidence_references"],
    }


def _credential(index: int, key_id: str, services: list[str], evidence_ids: list[str]) -> dict[str, Any]:
    return item("AKK", index, {"name": key_id, "services": ", ".join(services), "severity": "critical"}, "security_owner", evidence_ids, "Triage compromised API key", extra_keys=("services",))


def _strings(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        result = [compact(item) for item in value if compact(item)]
    elif value:
        result = [compact(value)]
    else:
        result = []
    return result or fallback
