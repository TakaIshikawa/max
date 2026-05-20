"""Generate deterministic audit evidence exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records, values


SCHEMA_VERSION = "max.spec.audit_evidence_exception_plan.v1"
KIND = "max.spec.audit_evidence_exception_plan"


def generate_audit_evidence_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "audit_evidence_exception")
    controls = values(hints.get("controls") or hints.get("control_ids"), ["primary audit control"])
    missing = unique_records(
        hints.get("missing_evidence") or hints.get("missing_evidence_items") or ctx["risks"],
        [
            {
                "name": "missing audit evidence",
                "owner": "control_owner",
                "description": "Track missing evidence and exception rationale.",
            }
        ],
    )
    compensating = unique_records(
        hints.get("compensating_controls"),
        [
            {
                "name": "compensating control",
                "owner": "control_owner",
                "description": "Document compensating control while evidence is unavailable.",
            }
        ],
    )
    owners = unique_records(
        hints.get("exception_owners") or hints.get("owners"),
        [
            {
                "name": compact(hints.get("exception_owner")) or "control owner",
                "owner": "audit_owner",
                "description": "Own exception remediation and review.",
            }
        ],
    )
    dates = unique_records(
        hints.get("expiration_review_dates")
        or hints.get("review_dates")
        or hints.get("expiration_dates"),
        [
            {
                "name": "exception review date",
                "owner": "audit_owner",
                "description": "Define expiration and review cadence for the evidence exception.",
            }
        ],
    )
    communications = unique_records(
        hints.get("auditor_communications") or hints.get("communications"),
        [
            {
                "name": "auditor exception notice",
                "owner": "audit_owner",
                "description": "Communicate exception rationale and compensating controls to auditors.",
            }
        ],
    )
    checks = unique_records(
        hints.get("validation_checks"),
        [
            {
                "name": "audit exception validation",
                "owner": "audit_owner",
                "description": "Validate controls, missing evidence, compensating controls, owners, dates, and auditor communications.",
            }
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx, control_count=len(controls), missing_evidence_count=len(missing)
        ),
        "controls": [
            _named("CTRL", index, item, "control_owner", evidence_ids)
            for index, item in enumerate(controls, start=1)
        ],
        "missing_evidence": [
            _item("MISS", index, item, "control_owner", evidence_ids)
            for index, item in enumerate(missing, start=1)
        ],
        "compensating_controls": [
            _item("COMP", index, item, "control_owner", evidence_ids)
            for index, item in enumerate(compensating, start=1)
        ],
        "exception_owners": [
            _item("OWN", index, item, "audit_owner", evidence_ids)
            for index, item in enumerate(owners, start=1)
        ],
        "expiration_review_dates": [
            _item("DATE", index, item, "audit_owner", evidence_ids)
            for index, item in enumerate(dates, start=1)
        ],
        "auditor_communications": [
            _item("COM", index, item, "audit_owner", evidence_ids)
            for index, item in enumerate(communications, start=1)
        ],
        "validation_checks": [
            _item("VC", index, item, "audit_owner", evidence_ids)
            for index, item in enumerate(checks, start=1)
        ],
        "evidence_references": ctx["evidence_references"],
    }


def _named(
    prefix: str, index: int, name: str, owner: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return row(prefix, index, name, owner, name, evidence_ids)


def _item(
    prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str]
) -> dict[str, Any]:
    return row(
        prefix,
        index,
        compact(item.get("name")),
        compact(item.get("owner")) or owner,
        compact(item.get("description")) or compact(item.get("name")),
        evidence_ids,
        severity=item.get("severity"),
        status=item.get("status"),
        review_date=item.get("review_date")
        or item.get("expiration")
        or item.get("expiry")
        or item.get("due"),
    )
