"""Generate deterministic API key rotation exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.api_key_rotation_exception_plan.v1"
KIND = "max.spec.api_key_rotation_exception_plan"
RISK_LEVELS = {"critical", "high", "medium", "low"}


def generate_api_key_rotation_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "api_key_rotation_exception")
    exceptions = [
        _exception(index, record, evidence_ids)
        for index, record in enumerate(
            unique_records(
                named(hints.get("exceptions") or hints.get("adapters") or hints.get("providers") or hints.get("publishers"), ("scope", "adapter", "provider", "publisher")),
                [{"name": "temporary API key rotation exception", "owner": "security_owner", "risk_level": "high"}],
            ),
            start=1,
        )
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, exception_count=len(exceptions)),
        "exception_scope": exceptions,
        "justification": section(hints, ("justification", "rationale"), "AKJ", "business_owner", "Document rotation exception justification", evidence_ids, ["time-boxed business or operational dependency requiring deferred API key rotation"]),
        "compensating_controls": section(hints, ("compensating_controls", "controls"), "AKC", "security_owner", "Operate compensating control", evidence_ids, ["restricted access, scoped permissions, usage monitoring, and alerting while rotation is deferred"]),
        "expiry_review": section(hints, ("expiry_review", "expiry", "review"), "AKE", "security_owner", "Review exception expiry", evidence_ids, ["review exception before expiry and confirm rotation date"]),
        "rollback": section(hints, ("rollback", "rollback_plan"), "AKR", "platform_owner", "Define rollback path", evidence_ids, ["revoke exception key, rotate credential, and restore standard rotation policy"]),
        "approval_criteria": section(hints, ("approval_criteria", "approvals", "approval_gates"), "AKA", "approval_owner", "Gate exception approval", evidence_ids, ["security, owner, and risk acceptance approval before exception starts"]),
        "verification_evidence": section(hints, ("verification_evidence", "evidence", "verification"), "AKV", "security_owner", "Capture verification evidence", evidence_ids, ["access review, monitoring proof, rotation ticket, and expiry review evidence"]),
        "evidence_references": ctx["evidence_references"],
    }


def _exception(index: int, record: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    risk_level = _risk(record.get("risk_level") or record.get("risk") or record.get("severity"))
    expiry = compact(record.get("expiry") or record.get("expiration") or record.get("expires_at")) or "30 days"
    scope = compact(record.get("scope") or record.get("adapter") or record.get("provider") or record.get("publisher") or record.get("name")) or "temporary API key rotation exception"
    return item(
        "AKX",
        index,
        {**record, "name": scope, "risk_level": risk_level, "expiry": expiry, "severity": risk_level},
        "security_owner",
        evidence_ids,
        "Review API key rotation exception",
        extra_keys=("scope", "adapter", "provider", "publisher", "risk_level"),
    )


def _risk(value: Any) -> str:
    text = compact(value).lower()
    return text if text in RISK_LEVELS else "high"
