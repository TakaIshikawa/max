"""Generate deterministic customer SLA credit review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records, values


SCHEMA_VERSION = "max.spec.customer_sla_credit_review_plan.v1"
KIND = "max.spec.customer_sla_credit_review_plan"


def generate_customer_sla_credit_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "customer_sla_credit_review")
    accounts = values(hints.get("affected_accounts") or hints.get("accounts"), [ctx["buyer"]])
    breaches = unique_records(
        hints.get("breach_records") or hints.get("breaches") or ctx["risks"],
        [
            {
                "name": "SLA breach review",
                "owner": "support_owner",
                "description": "Review SLA breach impact and credit status.",
            }
        ],
    )
    terms = unique_records(
        hints.get("credit_terms") or hints.get("contractual_credit_terms"),
        [
            {
                "name": "contractual credit terms",
                "owner": "legal_owner",
                "description": "Confirm SLA credit terms for affected accounts.",
            }
        ],
    )
    approvals = unique_records(
        hints.get("finance_approvals") or hints.get("approvals"),
        [
            {
                "name": "finance credit approval",
                "owner": "finance_owner",
                "description": "Approve credit calculations and account handling.",
            }
        ],
    )
    notices = unique_records(
        hints.get("customer_notices") or hints.get("notices"),
        [
            {
                "name": "SLA credit notice",
                "owner": "customer_success_owner",
                "description": "Notify affected accounts of SLA credit outcome.",
            }
        ],
    )
    links = unique_records(
        hints.get("remediation_links") or hints.get("remediations"),
        [
            {
                "name": "remediation tracking link",
                "owner": "engineering_owner",
                "description": "Link breach remediation evidence to credit review.",
            }
        ],
    )
    checks = unique_records(
        hints.get("validation_checks"),
        [
            {
                "name": "SLA credit validation",
                "owner": "finance_owner",
                "description": "Validate breach records, credit terms, approvals, notices, and remediation links.",
            }
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx, affected_account_count=len(accounts), breach_count=len(breaches)
        ),
        "affected_accounts": [
            _named("ACCT", index, item, "customer_success_owner", evidence_ids)
            for index, item in enumerate(accounts, start=1)
        ],
        "breach_records": [
            _item("BR", index, item, "support_owner", evidence_ids)
            for index, item in enumerate(breaches, start=1)
        ],
        "credit_terms": [
            _item("TERM", index, item, "legal_owner", evidence_ids)
            for index, item in enumerate(terms, start=1)
        ],
        "finance_approvals": [
            _item("APP", index, item, "finance_owner", evidence_ids)
            for index, item in enumerate(approvals, start=1)
        ],
        "customer_notices": [
            _item("NOT", index, item, "customer_success_owner", evidence_ids)
            for index, item in enumerate(notices, start=1)
        ],
        "remediation_links": [
            _item("REM", index, item, "engineering_owner", evidence_ids)
            for index, item in enumerate(links, start=1)
        ],
        "validation_checks": [
            _item("VC", index, item, "finance_owner", evidence_ids)
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
        status=item.get("status") or item.get("credit_status"),
        due=item.get("due") or item.get("deadline"),
        account=item.get("account"),
    )
