"""Generate deterministic vendor security reassessment plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.vendor_security_reassessment_plan.v1"
KIND = "max.spec.vendor_security_reassessment_plan"


def generate_vendor_security_reassessment_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "vendor_security_reassessment")
    vendors = unique_records(
        _named(hints.get("vendors") or hints.get("reassessments"), ("vendor",)),
        [
            {
                "name": "primary vendor reassessment",
                "owner": "vendor_owner",
                "severity": "medium",
                "due_status": "missing",
            }
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, vendor_count=len(vendors)),
        "vendor_reassessments": [_item("VSR", index, item, "vendor_owner", evidence_ids) for index, item in enumerate(vendors, start=1)],
        "risk_drivers": _section(hints, ("risk_drivers", "drivers"), "VSD", "risk_owner", "Assess risk driver", evidence_ids, ["incident, scope, or attestation driver"]),
        "evidence_gaps": _section(hints, ("evidence_gaps", "gaps"), "VSG", "vendor_owner", "Close evidence gap", evidence_ids, ["current security attestation"]),
        "control_reviews": _section(hints, ("controls", "control_reviews"), "VSC", "security_owner", "Review vendor control", evidence_ids, ["control review record"]),
        "approval_decisions": _section(hints, ("approval_outcomes", "approvals"), "VSA", "approval_owner", "Capture approval decision", evidence_ids, ["risk acceptance decision"]),
        "follow_up_actions": _section(hints, ("follow_up_actions", "actions"), "VSF", "vendor_owner", "Track follow-up action", evidence_ids, ["reassessment action log"]),
        "evidence_references": ctx["evidence_references"],
    }


def _section(hints: dict[str, Any], keys: tuple[str, ...], prefix: str, owner: str, label: str, evidence_ids: list[str], fallback: list[Any]) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return [_item(prefix, index, item, owner, evidence_ids, label) for index, item in enumerate(unique_records(value, fallback), start=1)]


def _item(prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str], label: str = "Review vendor security reassessment") -> dict[str, Any]:
    name = compact(item.get("name") or item.get("vendor"))
    return row(prefix, index, name, compact(item.get("owner")) or owner, compact(item.get("description")) or f"{label}: {name}.", evidence_ids, severity=compact(item.get("severity")) or "medium", status=compact(item.get("status") or item.get("due_status")) or "open", due=compact(item.get("due") or item.get("due_date")))


def _named(value: Any, aliases: tuple[str, ...]) -> Any:
    if not isinstance(value, list):
        return value
    result = []
    for item in value:
        if isinstance(item, dict) and not compact(item.get("name")):
            item = {**item, "name": next((compact(item.get(key)) for key in aliases if compact(item.get(key))), "")}
        result.append(item)
    return result
