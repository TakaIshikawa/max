"""Generate deterministic support escalation retention exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.support_escalation_retention_exception_plan.v1"
KIND = "max.spec.support_escalation_retention_exception_plan"


def generate_support_escalation_retention_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "support_escalation_retention_exception")
    records = unique_records(
        named(hints.get("retained_records") or hints.get("records") or hints.get("escalations"), ("record", "ticket", "customer")),
        [{"name": "support escalation retention exception", "owner": "support_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, retained_record_count=len(records)),
        "retained_records": [item("SER", index, record, "support_owner", evidence_ids, "Review retained support record", name_keys=("name", "record", "ticket", "customer"), extra_keys=("ticket", "customer", "escalation_id")) for index, record in enumerate(records, start=1)],
        "customer_scope": section(hints, ("customer_scope", "customers", "accounts"), "SEC", "support_owner", "Confirm customer escalation scope", evidence_ids, ["customer and escalation scope"]),
        "exception_rationale": section(hints, ("exception_rationale", "rationale", "justification"), "SEJ", "support_owner", "Document support retention exception rationale", evidence_ids, ["legal hold, escalation continuity, or customer commitment rationale"]),
        "privacy_controls": section(hints, ("privacy_controls", "controls"), "SEP", "privacy_owner", "Operate privacy control", evidence_ids, ["privacy owner review and data minimization control"]),
        "access_review": section(hints, ("access_review", "access_controls"), "SEA", "security_owner", "Review retained record access", evidence_ids, ["least-privilege support record access review"]),
        "retention_duration": section(hints, ("retention_duration", "duration", "expiry"), "SED", "privacy_owner", "Set retention duration", evidence_ids, ["90-day time-boxed retention period with owner review"], extra_keys=("duration", "expiry")),
        "purge_workflow": section(hints, ("purge_workflow", "purge", "deletion"), "SEX", "support_owner", "Purge retained support record", evidence_ids, ["scheduled purge workflow and completion evidence"]),
        "evidence_references": ctx["evidence_references"],
    }
