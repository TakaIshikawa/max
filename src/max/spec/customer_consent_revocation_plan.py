"""Generate deterministic customer consent revocation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.customer_consent_revocation_plan.v1"
KIND = "max.spec.customer_consent_revocation_plan"


def generate_customer_consent_revocation_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "customer_consent_revocation")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    consent_records = unique_records(
        named(
            hints.get("consent_scope") or hints.get("customers") or hints.get("consent_artifacts"),
            ("customer_id", "consent_artifact", "purpose"),
        ),
        [
            {
                "name": "customer consent revocation request",
                "customer_id": "unknown customer",
                "consent_artifact": "unknown consent artifact",
                "purpose": "all revoked processing purposes",
                "owner": "privacy_ops",
                "severity": "high",
            }
        ],
    )
    downstream_destinations = unique_records(
        named(
            hints.get("downstream_propagation")
            or hints.get("destinations")
            or hints.get("downstream_destinations"),
            ("destination", "system", "status"),
        ),
        [
            (
                "remove or suppress derived insights, exports, caches, publication targets, "
                "and partner destinations"
            )
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Customer Consent Revocation Plan",
        "summary": source_summary(ctx, consent_record_count=len(consent_records)),
        "consent_scope": [
            item(
                "CCR",
                index,
                record,
                "privacy_ops",
                evidence_ids,
                "Trace customer consent revocation scope",
                name_keys=("name", "customer_id", "consent_artifact", "purpose"),
                extra_keys=("customer_id", "consent_artifact", "purpose", "requested_at"),
            )
            for index, record in enumerate(consent_records, start=1)
        ],
        "affected_data_classes": section(
            hints,
            ("affected_data_classes", "data_classes", "records"),
            "CCD",
            "data_owner",
            "Identify consent-bound data class",
            evidence_ids,
            ["signals, feedback records, derived insights, exports, and publication destinations"],
        ),
        "revocation_workflow": section(
            hints,
            ("revocation_workflow", "workflow", "steps"),
            "CCW",
            "privacy_ops",
            "Execute consent revocation workflow",
            evidence_ids,
            [
                "validate request authority, mark consent ledger revoked, suppress future ingestion, "
                "and queue dependent records"
            ],
        ),
        "downstream_propagation": [
            item(
                "CCP",
                index,
                record,
                "integration_owner",
                evidence_ids,
                "Propagate consent revocation downstream",
                name_keys=("name", "destination", "system", "status"),
                extra_keys=("destination", "system", "status"),
            )
            for index, record in enumerate(downstream_destinations, start=1)
        ],
        "verification_evidence": section(
            hints,
            ("verification_evidence", "verification", "evidence"),
            "CCV",
            "quality_owner",
            "Verify consent revocation completion",
            evidence_ids,
            ["consent ledger diff, lineage query, downstream receipt, export suppression proof, and QA signoff"],
        ),
        "customer_communication": section(
            hints,
            ("customer_communication", "communications", "notifications"),
            "CCN",
            "customer_success_owner",
            "Communicate consent revocation status",
            evidence_ids,
            ["receipt confirmation, completion notice, exception explanation, and support contact"],
        ),
        "owner_checklist": section(
            hints,
            ("owner_checklist", "owners", "owner_matrix"),
            "CCO",
            "program_owner",
            "Complete consent revocation owner checklist",
            evidence_ids,
            ["privacy, data, integration, customer success, and compliance owner signoffs"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
