"""Generate deterministic customer deprovisioning exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.customer_deprovisioning_exception_plan.v1"
KIND = "max.spec.customer_deprovisioning_exception_plan"


def generate_customer_deprovisioning_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "customer_deprovisioning_exception")
    retained = unique_records(
        named(
            hints.get("retained_access") or hints.get("accounts") or hints.get("workspaces"),
            ("account", "workspace", "customer", "user"),
        ),
        [{"name": "retained customer access exception", "owner": "customer_owner", "severity": "high"}],
    )
    expiration = section(hints, ("expiration", "expiration_date", "expiry"), "CDE", "customer_owner", "Set deprovisioning exception expiration", evidence_ids, ["expiration date required before exception approval"], extra_keys=("expiration", "expiry", "deadline"))
    missing_expiration = not any(key in hints for key in ("expiration", "expiration_date", "expiry"))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, retained_access_count=len(retained)),
        "exception_rationale": section(hints, ("rationale", "exception_rationale", "justification"), "CDR", "customer_owner", "Document deprovisioning exception rationale", evidence_ids, ["time-boxed contractual, legal hold, billing, or migration rationale"]),
        "retained_access": [
            item(
                "CDA",
                index,
                record,
                "customer_owner",
                evidence_ids,
                "Review retained customer access",
                name_keys=("name", "account", "workspace", "customer", "user"),
                extra_keys=("account", "workspace", "customer", "user", "role"),
            )
            for index, record in enumerate(retained, start=1)
        ],
        "compensating_controls": section(hints, ("controls", "compensating_controls"), "CDC", "security_owner", "Operate compensating control", evidence_ids, ["least privilege, access logging, disabled automation, and daily owner review"]),
        "expiration": expiration,
        "required_follow_up": [
            {
                "id": "CDF1",
                "name": "Expiration date required",
                "owner": "customer_owner",
                "description": "Customer deprovisioning exceptions require an explicit expiration date before approval.",
                "evidence_reference_ids": evidence_ids,
                "severity": "high",
            }
        ] if missing_expiration else [],
        "owner_approvals": section(hints, ("approvals", "owner_approvals", "approvers"), "CDO", "approval_owner", "Capture owner approval", evidence_ids, ["customer owner, security, support, legal, and compliance approval"]),
        "customer_notification": section(hints, ("notification", "customer_notification", "notices"), "CDN", "customer_owner", "Notify customer about deprovisioning exception", evidence_ids, ["customer-facing exception notice, expiration date, and support contact"]),
        "audit_evidence": section(hints, ("audit_evidence", "evidence", "audit"), "CDV", "compliance_owner", "Collect audit evidence", evidence_ids, ["ticket, approval, access log, notification, and deprovisioning completion proof"]),
        "evidence_references": ctx["evidence_references"],
    }
