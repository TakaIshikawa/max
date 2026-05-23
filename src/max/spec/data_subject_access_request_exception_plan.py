"""Generate deterministic data subject access request exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.data_subject_access_request_exception_plan.v1"
KIND = "max.spec.data_subject_access_request_exception_plan"


def generate_data_subject_access_request_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "data_subject_access_request_exception")
    requests = unique_records(
        named(hints.get("request_scope") or hints.get("requests") or hints.get("subjects"), ("request", "subject", "requester")),
        [{"name": "data subject access request exception", "owner": "privacy_owner", "severity": "high"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, request_count=len(requests)),
        "request_scope": [item("DSR", index, record, "privacy_owner", evidence_ids, "Review DSAR exception request", name_keys=("name", "request", "subject", "requester"), extra_keys=("subject", "requester", "jurisdiction")) for index, record in enumerate(requests, start=1)],
        "exception_rationale": section(hints, ("exception_rationale", "rationale", "justification"), "DSJ", "privacy_owner", "Document DSAR exception rationale", evidence_ids, ["legal, identity, security, or data availability rationale"]),
        "affected_data_categories": section(hints, ("affected_data_categories", "data_categories", "categories"), "DSD", "privacy_owner", "Confirm affected data category", evidence_ids, ["profile data category"], extra_keys=("category", "classification")),
        "legal_privacy_review": section(hints, ("legal_privacy_review", "reviewers", "review"), "DSL", "privacy_owner", "Complete legal/privacy review", evidence_ids, ["privacy owner and legal reviewer path"]),
        "compensating_controls": section(hints, ("compensating_controls", "controls"), "DSC", "privacy_owner", "Operate DSAR compensating control", evidence_ids, ["requester identity verification and restricted handling"]),
        "requester_communication": section(hints, ("requester_communication", "communications", "notices"), "DSN", "privacy_owner", "Communicate DSAR exception", evidence_ids, ["requester notice with exception reason and next response date"]),
        "remediation_workflow": section(hints, ("remediation_workflow", "expiry", "remediation"), "DSX", "privacy_owner", "Remediate DSAR exception", evidence_ids, ["expiry, response, or remediation workflow"]),
        "evidence_references": ctx["evidence_references"],
    }
