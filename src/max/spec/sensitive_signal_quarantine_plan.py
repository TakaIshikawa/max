"""Generate deterministic sensitive signal quarantine plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.sensitive_signal_quarantine_plan.v1"
KIND = "max.spec.sensitive_signal_quarantine_plan"


def generate_sensitive_signal_quarantine_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "sensitive_signal_quarantine")
    categories = unique_records(
        named(
            hints.get("quarantined_signal_categories") or hints.get("categories") or hints.get("signals") or hints.get("signal_categories"),
            ("category", "source", "signal", "data_class"),
        ),
        [{"name": "sensitive signal category pending reviewer disposition", "owner": "privacy_owner", "severity": "high", "retention": "quarantine until purge or release decision"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, quarantined_signal_category_count=len(categories)),
        "quarantined_signal_categories": [
            item(
                "SSQ",
                index,
                record,
                "privacy_owner",
                evidence_ids,
                "Review quarantined sensitive signal category",
                name_keys=("name", "category", "source", "signal", "data_class"),
                extra_keys=("source", "category", "signal", "data_class", "retention"),
            )
            for index, record in enumerate(categories, start=1)
        ],
        "detection_triggers": section(hints, ("detection_triggers", "triggers", "detectors"), "SST", "security_owner", "Detect sensitive signal", evidence_ids, ["PII, credential, health, financial, or customer-confidential signal trigger"]),
        "isolation_controls": section(hints, ("isolation_controls", "controls", "quarantine_controls"), "SSI", "security_owner", "Isolate quarantined signal", evidence_ids, ["deny indexing, mask payload, restrict access, and encrypt quarantine store"]),
        "reviewer_workflow": section(hints, ("reviewer_workflow", "reviewers", "review_workflow"), "SSR", "privacy_owner", "Review quarantined signal", evidence_ids, ["privacy, security, and data owner review workflow"]),
        "purge_release_criteria": section(hints, ("purge_release_criteria", "purge_release", "criteria"), "SSP", "privacy_owner", "Decide purge or release", evidence_ids, ["purge sensitive payloads or release only after approved redaction"]),
        "audit_logging": section(hints, ("audit_logging", "audit", "logs"), "SSA", "compliance_owner", "Log quarantine decision", evidence_ids, ["log detection, reviewer, access, purge, release, and notification events"]),
        "notification_plan": section(hints, ("notification_plan", "notifications", "notification"), "SSN", "support_owner", "Notify stakeholders", evidence_ids, ["notify data owner, privacy, security, and customer contact when required"]),
        "evidence_references": ctx["evidence_references"],
    }
