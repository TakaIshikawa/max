"""Generate deterministic SAML assertion mapping review plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.saml_assertion_mapping_review_plan.v1"
KIND = "max.spec.saml_assertion_mapping_review_plan"


def generate_saml_assertion_mapping_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "saml_assertion_mapping_review")
    mappings = unique_records(
        named(
            hints.get("mappings") or hints.get("attribute_mappings") or hints.get("assertion_mappings"),
            ("attribute", "claim", "target_field", "idp"),
        ),
        [{"name": "missing SAML assertion mapping", "owner": "identity_owner", "severity": "high", "status": "missing"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, mapping_count=len(mappings)),
        "identity_provider_scope": section(hints, ("idps", "identity_providers", "identity_provider_scope"), "SAMIDP", "identity_owner", "Confirm identity provider scope", evidence_ids, ["identity provider tenant, app, signing certificate, and customer realm"], extra_keys=("idp", "tenant", "customer")),
        "attribute_mappings": [
            item(
                "SAM",
                index,
                record,
                "identity_owner",
                evidence_ids,
                "Review SAML assertion mapping",
                name_keys=("name", "attribute", "claim", "target_field", "idp"),
                extra_keys=("attribute", "claim", "target_field", "transform", "status"),
            )
            for index, record in enumerate(mappings, start=1)
        ],
        "validation_warnings": [
            {
                "id": "SAMW1",
                "name": "SAML assertion mappings required",
                "owner": "identity_owner",
                "description": "No explicit SAML assertion mappings were supplied; validate required claims before launch.",
                "evidence_reference_ids": evidence_ids,
                "severity": "high",
            }
        ] if not any(key in hints for key in ("mappings", "attribute_mappings", "assertion_mappings")) else [],
        "required_claims": section(hints, ("required_claims", "claims"), "SAMC", "identity_owner", "Verify required SAML claim", evidence_ids, ["NameID, email, subject, groups, and tenant entitlement claims"]),
        "test_users": section(hints, ("test_users", "users", "personas"), "SAMU", "qa_owner", "Validate SAML test user", evidence_ids, ["admin, standard user, disabled user, and unmapped group test personas"], extra_keys=("email", "role", "group")),
        "rollback": section(hints, ("rollback", "rollback_plan", "backout"), "SAMB", "identity_owner", "Rollback SAML mapping change", evidence_ids, ["restore previous assertion mappings and disable new SSO app assignment"]),
        "customer_coordination": section(hints, ("customer_coordination", "coordination", "customers"), "SAMQ", "customer_owner", "Coordinate SAML mapping review with customer", evidence_ids, ["customer IdP admin validation window and sign-off"]),
        "approval_evidence": section(hints, ("approval_evidence", "approvals", "evidence"), "SAMA", "approval_owner", "Capture SAML approval evidence", evidence_ids, ["identity, security, customer, and support readiness approval"]),
        "evidence_references": ctx["evidence_references"],
    }
