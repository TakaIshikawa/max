"""Generate deterministic incident customer credit review plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.incident_customer_credit_review_plan.v1"
KIND = "max.spec.incident_customer_credit_review_plan"


def generate_incident_customer_credit_review_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "incident_customer_credit_review")
    credits = unique_records(
        _named(hints.get("affected_customers") or hints.get("credits"), ("customer", "incident")),
        [
            {
                "name": ctx["buyer"],
                "owner": "customer_success_owner",
                "severity": "medium",
                "credit_status": "pending",
            }
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, customer_count=len(credits)),
        "customer_credit_records": [_item("ICR", index, item, "customer_success_owner", evidence_ids) for index, item in enumerate(credits, start=1)],
        "incident_impact": _section(hints, ("incidents", "impact_windows", "incident_impact"), "ICI", "incident_owner", "Confirm incident impact", evidence_ids, ["incident impact window"]),
        "sla_eligibility": _section(hints, ("sla_terms", "eligibility"), "ICS", "legal_owner", "Review SLA eligibility", evidence_ids, ["contractual SLA terms"]),
        "proposed_credits": _section(hints, ("proposed_credits", "credits"), "ICP", "finance_owner", "Calculate proposed credit", evidence_ids, ["credit calculation"]),
        "approval_gates": _section(hints, ("approvers", "approvals"), "ICA", "approval_owner", "Capture credit approval", evidence_ids, ["finance approval"]),
        "customer_communications": _section(hints, ("communications", "customer_communications"), "ICC", "customer_success_owner", "Send customer communication", evidence_ids, ["customer credit notice"]),
        "evidence_references": ctx["evidence_references"],
    }


def _section(hints: dict[str, Any], keys: tuple[str, ...], prefix: str, owner: str, label: str, evidence_ids: list[str], fallback: list[Any]) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return [_item(prefix, index, item, owner, evidence_ids, label) for index, item in enumerate(unique_records(value, fallback), start=1)]


def _item(prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str], label: str = "Review incident customer credit") -> dict[str, Any]:
    name = compact(item.get("name") or item.get("customer") or item.get("incident"))
    return row(prefix, index, name, compact(item.get("owner")) or owner, compact(item.get("description")) or f"{label}: {name}.", evidence_ids, severity=compact(item.get("severity")) or "medium", status=compact(item.get("status") or item.get("credit_status")) or "pending", incident=compact(item.get("incident")), impact_window=compact(item.get("impact_window")), proposed_credit=compact(item.get("proposed_credit")))


def _named(value: Any, aliases: tuple[str, ...]) -> Any:
    if not isinstance(value, list):
        return value
    result = []
    for item in value:
        if isinstance(item, dict) and not compact(item.get("name")):
            item = {**item, "name": next((compact(item.get(key)) for key in aliases if compact(item.get(key))), "")}
        result.append(item)
    return result
