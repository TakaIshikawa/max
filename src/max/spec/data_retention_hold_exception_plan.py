"""Generate deterministic data retention hold exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.data_retention_hold_exception_plan.v1"
KIND = "max.spec.data_retention_hold_exception_plan"


def generate_data_retention_hold_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "data_retention_hold_exception")
    held_records = unique_records(
        named(
            hints.get("held_records") or hints.get("records") or hints.get("held_datasets") or hints.get("datasets"),
            ("record", "dataset", "table", "account", "system"),
        ),
        [{"name": "records under legal or audit retention hold", "owner": "retention_owner", "severity": "high", "duration": "until hold release"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, held_record_count=len(held_records)),
        "held_records": [
            item(
                "DRH",
                index,
                record,
                "retention_owner",
                evidence_ids,
                "Review retained record hold",
                name_keys=("name", "record", "dataset", "table", "account", "system"),
                extra_keys=("record", "dataset", "table", "account", "system", "duration", "legal_basis", "audit_reason"),
            )
            for index, record in enumerate(held_records, start=1)
        ],
        "hold_rationale": section(hints, ("hold_rationale", "rationale", "legal_rationale", "audit_rationale", "justification"), "DRJ", "legal_owner", "Document retention hold rationale", evidence_ids, ["legal, audit, or investigation rationale for preserving records"], extra_keys=("duration", "legal_basis", "audit_reason")),
        "hold_duration": section(hints, ("hold_duration", "duration", "retention_duration", "retention_window"), "DRD", "retention_owner", "Confirm retention hold duration", evidence_ids, ["hold remains active until legal or audit release"], extra_keys=("duration", "expires_at", "expiry")),
        "retention_owner": section(hints, ("retention_owner", "owners", "owner"), "DRO", "retention_owner", "Assign retention hold owner", evidence_ids, ["named retention owner accountable for hold review and release"]),
        "controls": section(hints, ("controls", "compensating_controls", "safeguards"), "DRC", "security_owner", "Operate compensating control", evidence_ids, ["access restriction, encryption, audit logging, and purpose-bound handling"]),
        "review_cadence": section(hints, ("review_cadence", "cadence", "reviews", "review_schedule"), "DRV", "privacy_owner", "Review retention hold", evidence_ids, ["monthly legal, audit, and privacy review cadence"], extra_keys=("cadence", "review_date")),
        "expiry_workflow": section(hints, ("expiry_workflow", "expiry", "expiration", "release_workflow"), "DRX", "retention_owner", "Release or renew retention hold", evidence_ids, ["release, delete, or renew held records before hold expiry"], extra_keys=("duration", "expires_at", "expiry")),
        "evidence_references": ctx["evidence_references"],
    }
