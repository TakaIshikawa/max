"""Generate deterministic billing impact review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records, values


SCHEMA_VERSION = "max.spec.billing_impact_review_plan.v1"
KIND = "max.spec.billing_impact_review_plan"


def generate_billing_impact_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "billing_impact_review")
    affected_plans = values(
        hints.get("affected_plans") or hints.get("plans"), ["default subscription plan"]
    )
    risks = unique_records(
        hints.get("charge_risks") or hints.get("billing_risks") or ctx["risks"],
        [
            {
                "name": "billing impact review",
                "owner": "billing_owner",
                "description": "Confirm charge behavior before release.",
            }
        ],
    )
    actions = unique_records(
        hints.get("refund_credit_actions")
        or hints.get("refund_actions")
        or hints.get("credit_actions"),
        [
            {
                "name": "refund and credit decision",
                "owner": "finance_owner",
                "description": "Define whether impacted invoices need refunds, credits, or no action.",
            }
        ],
    )
    approvals = unique_records(
        hints.get("owner_approvals") or hints.get("approvals"),
        [
            {
                "name": "billing and finance approval",
                "owner": compact(hints.get("approval_owner")) or "finance_owner",
                "description": "Approve affected plans, charge risks, and refund or credit actions.",
            }
        ],
    )
    communications = unique_records(
        hints.get("customer_communications") or hints.get("communications"),
        [
            {
                "name": "billing impact notice",
                "owner": "customer_success_owner",
                "description": "Prepare customer-facing billing impact guidance.",
            }
        ],
    )
    checks = unique_records(
        hints.get("validation_checks"),
        [
            {
                "name": "invoice preview validation",
                "owner": "billing_owner",
                "description": "Validate affected plan charges, credits, and approvals before launch.",
            }
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx, affected_plan_count=len(affected_plans), charge_risk_count=len(risks)
        ),
        "affected_plans": [
            _named("PLAN", index, plan, "billing_owner", evidence_ids)
            for index, plan in enumerate(affected_plans, start=1)
        ],
        "charge_risks": [
            _item("RISK", index, item, "billing_owner", evidence_ids)
            for index, item in enumerate(risks, start=1)
        ],
        "refund_credit_actions": [
            _item("RC", index, item, "finance_owner", evidence_ids)
            for index, item in enumerate(actions, start=1)
        ],
        "owner_approvals": [
            _item("APP", index, item, "finance_owner", evidence_ids)
            for index, item in enumerate(approvals, start=1)
        ],
        "customer_communications": [
            _item("COM", index, item, "customer_success_owner", evidence_ids)
            for index, item in enumerate(communications, start=1)
        ],
        "validation_checks": [
            _item("VC", index, item, "billing_owner", evidence_ids)
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
        compact(item.get("description"))
        or compact(item.get("action"))
        or compact(item.get("name")),
        evidence_ids,
        severity=item.get("severity"),
        status=item.get("status") or item.get("credit_status") or item.get("due_status"),
        due=item.get("due") or item.get("deadline"),
        amount=item.get("amount"),
    )
