"""Generate deterministic data deletion verification plans for TactSpec previews."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.data_deletion_verification_plan.v1"
DATA_DELETION_VERIFICATION_PLAN_SCHEMA_VERSION = SCHEMA_VERSION
KIND = "max.spec.data_deletion_verification_plan"


def generate_data_deletion_verification_plan(spec_like: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic verification guidance for customer data deletion completion."""
    ctx = context(spec_like if isinstance(spec_like, dict) else {})
    evidence_ids = [item["id"] for item in ctx["evidence_references"]]
    deletion_scope = _deletion_scope(ctx, spec_like)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(
            ctx,
            deletion_scope_count=len(deletion_scope),
            verification_check_count=4,
            evidence_requirement_count=4,
            exception_count=3,
        ),
        "deletion_scope": deletion_scope,
        "verification_checks": _verification_checks(ctx, deletion_scope, evidence_ids),
        "evidence_requirements": _evidence_requirements(ctx, evidence_ids),
        "owner_roles": _owner_roles(ctx),
        "exception_handling": _exception_handling(ctx, evidence_ids),
        "evidence_references": ctx["evidence_references"],
    }


def _deletion_scope(ctx: dict[str, Any], spec_like: dict[str, Any]) -> list[dict[str, Any]]:
    spec = spec_like if isinstance(spec_like, dict) else {}
    privacy = spec.get("privacy") if isinstance(spec.get("privacy"), dict) else {}
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    explicit_scope = string_list(
        privacy.get("deletion_scope")
        or privacy.get("data_deletion_scope")
        or metadata.get("deletion_scope")
        or metadata.get("data_scope")
    )
    if not explicit_scope:
        explicit_scope = [
            f"Customer records for {ctx['workflow_context']}",
            "Account identifiers, submitted workflow data, exports, logs, and integration copies.",
        ]

    return [
        {
            "id": f"DS{index}",
            "name": scope,
            "category": _scope_category(scope),
            "deletion_trigger": "customer deletion request or contract termination",
            "owner": "data_owner" if index == 1 else "technical_owner",
            "verification_target": "No recoverable customer data remains in production, backups past expiry, analytics, or processors.",
            "references": ["project.workflow_context", "execution.mvp_scope"],
        }
        for index, scope in enumerate(explicit_scope, start=1)
    ]


def _verification_checks(
    ctx: dict[str, Any], deletion_scope: list[dict[str, Any]], evidence_ids: list[str]
) -> list[dict[str, Any]]:
    scope_refs = [item["id"] for item in deletion_scope]
    title = ctx["title"]
    workflow = ctx["workflow_context"]
    return [
        _check(
            "VC1",
            "Source system deletion",
            "data_owner",
            "Confirm primary application records and object storage for the deletion subject are removed.",
            "query primary stores for subject identifiers returns zero active records",
            scope_refs,
            evidence_ids,
        ),
        _check(
            "VC2",
            "Derived data purge",
            "engineering_owner",
            f"Verify caches, search indexes, analytics events, exports, and AI-derived artifacts for {workflow}.",
            "derived stores contain no subject-identifying payloads after purge job completion",
            scope_refs,
            evidence_ids,
        ),
        _check(
            "VC3",
            "Processor confirmation",
            "privacy_owner",
            f"Collect deletion or anonymization confirmation from subprocessors used by {title}.",
            "processor receipts are attached or exception is approved before closure",
            scope_refs,
            evidence_ids,
        ),
        _check(
            "VC4",
            "Closure audit trail",
            "compliance_owner",
            "Review timestamps, approvers, sampled queries, and customer-facing confirmation before closing the request.",
            "verification packet has owner approval and immutable audit evidence",
            scope_refs,
            evidence_ids,
        ),
    ]


def _evidence_requirements(ctx: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        _requirement(
            "ER1",
            "Deletion request record",
            "privacy_owner",
            f"Capture requester, scope, authorization, and due date for {ctx['target_user']}.",
            evidence_ids,
        ),
        _requirement(
            "ER2",
            "System query proof",
            "data_owner",
            "Retain redacted before/after query results or job logs for every in-scope datastore.",
            evidence_ids,
        ),
        _requirement(
            "ER3",
            "Processor receipts",
            "vendor_owner",
            "Attach subprocessor deletion confirmations, anonymization receipts, or documented non-applicability notes.",
            evidence_ids,
        ),
        _requirement(
            "ER4",
            "Customer confirmation",
            "support_owner",
            "Store final customer notice with scope, completion date, and any approved exception language.",
            evidence_ids,
        ),
    ]


def _owner_roles(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": "privacy_owner",
            "suggested_owner": ctx["buyer"],
            "responsibility": "Approve scope, exceptions, and customer-facing completion language.",
        },
        {
            "role": "data_owner",
            "suggested_owner": "data_owner",
            "responsibility": "Run datastore inventory checks and retain query proof.",
        },
        {
            "role": "engineering_owner",
            "suggested_owner": "technical_owner",
            "responsibility": "Execute purge jobs for derived stores, backups, exports, and integrations.",
        },
        {
            "role": "support_owner",
            "suggested_owner": "support_owner",
            "responsibility": "Coordinate requester communication and closure tracking.",
        },
    ]


def _exception_handling(ctx: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [
        _exception(
            "EX1",
            "Legal retention hold",
            "legal_owner",
            "Pause deletion for records under statutory, contractual, security, or finance retention obligations.",
            "Document retained categories, legal basis, review date, and customer-safe explanation.",
            evidence_ids,
        ),
        _exception(
            "EX2",
            "Backup expiry window",
            "security_owner",
            "If immutable backups cannot be selectively deleted, record expiry timing and restoration suppression controls.",
            "Confirm backups age out under retention policy and restored data would be re-deleted before access.",
            evidence_ids,
        ),
        _exception(
            "EX3",
            "Unverified requester",
            "privacy_owner",
            f"Do not process deletion for {ctx['workflow_context']} until requester authority is verified.",
            "Keep intake evidence and close or re-open only after identity verification succeeds.",
            evidence_ids,
        ),
    ]


def _check(
    item_id: str,
    name: str,
    owner: str,
    description: str,
    success_criteria: str,
    scope_refs: list[str],
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "description": description,
        "success_criteria": success_criteria,
        "scope_references": scope_refs,
        "evidence_reference_ids": evidence_ids,
    }


def _requirement(
    item_id: str, name: str, owner: str, description: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "description": description,
        "retention": "retain with privacy audit evidence for the approved compliance period",
        "evidence_reference_ids": evidence_ids,
    }


def _exception(
    item_id: str,
    name: str,
    owner: str,
    condition: str,
    required_action: str,
    evidence_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "owner": owner,
        "condition": condition,
        "required_action": required_action,
        "evidence_reference_ids": evidence_ids,
    }


def _scope_category(scope: str) -> str:
    lowered = compact(scope).lower()
    if any(term in lowered for term in ("log", "analytics", "event", "telemetry")):
        return "logs_and_telemetry"
    if any(term in lowered for term in ("processor", "vendor", "integration", "subprocessor")):
        return "processor_copy"
    if any(term in lowered for term in ("backup", "archive")):
        return "backup_or_archive"
    if any(term in lowered for term in ("export", "report", "download")):
        return "exported_artifact"
    return "customer_data"
