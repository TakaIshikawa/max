"""Generate deterministic incident customer notification plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records

SCHEMA_VERSION = "max.spec.incident_customer_notification_plan.v1"
KIND = "max.spec.incident_customer_notification_plan"

TIMING_BY_SEVERITY = {
    "sev0": "notify within 15 minutes, then every 30 minutes until mitigated",
    "sev1": "notify within 30 minutes, then hourly until mitigated",
    "sev2": "notify within 2 hours, then at material status changes",
    "sev3": "notify in the next scheduled customer update",
}


def generate_incident_customer_notification_plan(inputs: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(inputs, "incident_customer_notification")
    severity = _severity(hints)
    segments = unique_records(named(hints.get("audience_segments") or hints.get("segments"), ("segment", "customer_type", "name")), [{"segment": "all impacted customers", "customer_type": "standard"}])
    audience_segments = [_segment_row(record, index, evidence_ids) for index, record in enumerate(segments, start=1)]
    escalated = [record for record in audience_segments if record["approval_required"] or record["evidence_required"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, severity=severity, audience_segment_count=len(audience_segments), escalated_segment_count=len(escalated)),
        "severity": severity,
        "timing_sla": TIMING_BY_SEVERITY.get(severity, TIMING_BY_SEVERITY["sev2"]),
        "audience_segments": audience_segments,
        "notification_triggers": section(hints, ("notification_triggers", "triggers"), "ICN", "incident_commander", "Define customer notification trigger", evidence_ids, ["confirmed customer impact", "regulatory reporting threshold met"]),
        "channel_matrix": section(hints, ("channel_matrix", "channels"), "ICC", "customer_success_owner", "Map notification channel", evidence_ids, ["status page, email, support macro, and account-team outreach"], extra_keys=("channel", "segment")),
        "approval_chain": section(hints, ("approval_chain", "approvals"), "ICA", "communications_owner", "Approve incident customer communication", evidence_ids, ["incident commander, legal/privacy, support lead, and executive sponsor for regulated customers"]),
        "faq_evidence_needs": section(hints, ("faq_evidence_needs", "faq_evidence", "evidence_needs"), "ICF", "support_owner", "Prepare incident FAQ evidence", evidence_ids, ["impact window, affected features, mitigation status, data exposure determination, and remediation commitments"]),
        "post_incident_follow_up": section(hints, ("post_incident_follow_up", "follow_up"), "ICP", "customer_success_owner", "Send post-incident follow-up", evidence_ids, ["final RCA, prevention actions, SLA credit path, and customer-specific evidence package"]),
        "escalated_segments": escalated,
        "evidence_references": ctx["evidence_references"],
    }


def _severity(hints: dict[str, Any]) -> str:
    raw = compact(hints.get("severity") or hints.get("incident_severity") or "sev2").lower().replace(" ", "")
    aliases = {"critical": "sev0", "p0": "sev0", "high": "sev1", "p1": "sev1", "medium": "sev2", "p2": "sev2", "low": "sev3", "p3": "sev3"}
    return aliases.get(raw, raw if raw in TIMING_BY_SEVERITY else "sev2")


def _segment_row(record: dict[str, Any], index: int, evidence_ids: list[str]) -> dict[str, Any]:
    segment = compact(record.get("segment") or record.get("customer_type") or record.get("name")) or "all impacted customers"
    text = " ".join(compact(record.get(key)).lower() for key in ("segment", "customer_type", "tier", "regulatory_status", "contract_type"))
    escalated = any(term in text for term in ("regulated", "enterprise", "financial", "healthcare", "hipaa", "sox"))
    return row("ICS", index, segment, compact(record.get("owner")) or "customer_success_owner", "Prepare customer-facing incident notification path.", evidence_ids, customer_type=compact(record.get("customer_type") or record.get("tier")) or "standard", approval_required=escalated, evidence_required=escalated, evidence_needs="legal/privacy approved impact evidence and customer-specific FAQ" if escalated else "standard impact summary and support FAQ")
