"""Generate deterministic model access deprovisioning plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.model_access_deprovisioning_plan.v1"
KIND = "max.spec.model_access_deprovisioning_plan"


def generate_model_access_deprovisioning_plan(spec_like: Any) -> dict[str, Any]:
    """Return a stable plan to remove model provider access."""
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_access_deprovisioning")
    subjects = unique_records(
        named(hints.get("access_subjects") or hints.get("subjects") or hints.get("users") or hints.get("services"), ("subject", "user", "service")),
        [{"name": "model provider access subjects", "access": "provider credentials"}],
    )
    exceptions = unique_records(
        named(hints.get("exceptions") or hints.get("approved_exceptions"), ("subject", "user", "service")),
        [],
    )
    blockers = _blockers(subjects, exceptions, evidence_ids)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, subject_count=len(subjects), exception_count=len(exceptions), blocker_count=len(blockers)),
        "access_subjects": [
            item("MAD", index, record, "identity_owner", evidence_ids, "Review model access subject", name_keys=("name", "subject", "user", "service"), extra_keys=("access", "provider", "last_used", "exception_id"))
            for index, record in enumerate(subjects, start=1)
        ],
        "revocation_tasks": section(hints, ("revocation_tasks", "revocations"), "MAR", "identity_owner", "Revoke model access", evidence_ids, ["remove user and service account access to model providers", "revoke API keys and tokens"]),
        "allowlist_updates": section(hints, ("allowlist_updates", "allowlists"), "MAW", "platform_owner", "Update model access allowlist", evidence_ids, ["remove retired subjects from provider and gateway allowlists"]),
        "audit_validation": section(hints, ("audit_validation", "audit_logs", "validation"), "MAV", "compliance_owner", "Validate model access audit logs", evidence_ids, ["audit log confirms revocation, key disablement, and denied access attempts"]),
        "exception_handling": [
            item("MAE", index, record, "risk_owner", evidence_ids, "Document model access exception", name_keys=("name", "subject", "user", "service"), extra_keys=("reason", "expiry", "approved_by"))
            for index, record in enumerate(exceptions, start=1)
        ],
        "blockers": blockers,
        "evidence_references": ctx["evidence_references"],
    }


def _blockers(subjects: list[dict[str, Any]], exceptions: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    exception_names = {compact(item.get("name")).casefold() for item in exceptions}
    blockers: list[dict[str, Any]] = []
    for subject in subjects:
        name = compact(subject.get("name"))
        status = compact(subject.get("status") or subject.get("access")).lower()
        lingering = any(term in status for term in ("active", "lingering", "not revoked", "remaining"))
        has_exception = compact(subject.get("exception_id")) or name.casefold() in exception_names
        if lingering and not has_exception:
            blockers.append(row("MAK", len(blockers) + 1, f"{name} lingering access", "identity_owner", "Lingering model provider access must be revoked or tied to an approved exception.", evidence_ids, severity="critical"))
    return blockers
