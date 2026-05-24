"""Generate deterministic vendor data deletion attestation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.vendor_data_deletion_attestation_plan.v1"
KIND = "max.spec.vendor_data_deletion_attestation_plan"


def generate_vendor_data_deletion_attestation_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "vendor_data_deletion_attestation")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    vendors = unique_records(
        named(hints.get("vendors") or hints.get("vendor_scope") or hints.get("processors"), ("vendor", "contact", "data_category")),
        [
            {
                "name": "unassigned vendor",
                "vendor": "unassigned vendor",
                "contact": "vendor account owner",
                "due_date": "next attestation cycle",
                "severity": "high",
            }
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Vendor Data Deletion Attestation Plan",
        "summary": source_summary(ctx, vendor_count=len(vendors)),
        "vendor_scope": [
            item(
                "VDA",
                index,
                record,
                "vendor_manager",
                evidence_ids,
                "Obtain vendor deletion attestation",
                name_keys=("name", "vendor", "processor"),
                extra_keys=("vendor", "contact", "due_date", "data_category", "system"),
            )
            for index, record in enumerate(vendors, start=1)
        ],
        "data_categories": section(
            hints,
            ("data_categories", "categories", "data_classes"),
            "VDC",
            "data_owner",
            "Confirm vendor deletion data category",
            evidence_ids,
            ["shared signals, generated insights, customer records, exports, and support attachments"],
        ),
        "attestation_request_steps": section(
            hints,
            ("attestation_request_steps", "request_steps", "steps"),
            "VDR",
            "vendor_manager",
            "Request vendor deletion attestation",
            evidence_ids,
            [
                "send deletion scope, due date, required evidence, retention exception template, "
                "and escalation contact"
            ],
        ),
        "evidence_review": section(
            hints,
            ("evidence_review", "evidence", "evidence_items"),
            "VDE",
            "privacy_owner",
            "Review vendor deletion evidence",
            evidence_ids,
            ["signed attestation, deletion job receipt, residual data exception log, and reviewer signoff"],
        ),
        "exception_handling": section(
            hints,
            ("exception_handling", "exceptions", "exception_plan"),
            "VDX",
            "privacy_owner",
            "Handle vendor deletion attestation exception",
            evidence_ids,
            ["document retained data, legal basis, expiry, compensating controls, and customer impact"],
            extra_keys=("exception", "expiry", "status"),
        ),
        "escalation": section(
            hints,
            ("escalation", "escalations", "late_attestations"),
            "VDL",
            "program_owner",
            "Escalate missing vendor attestation",
            evidence_ids,
            ["notify vendor owner at due date, escalate to procurement, then privacy and legal"],
        ),
        "closure_criteria": section(
            hints,
            ("closure_criteria", "closure", "acceptance_criteria"),
            "VDQ",
            "privacy_owner",
            "Close vendor deletion attestation",
            evidence_ids,
            ["all attestations received, exceptions approved, evidence archived, and requester notified"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
