"""Generate deterministic customer data correction plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.customer_data_correction_plan.v1"
KIND = "max.spec.customer_data_correction_plan"


def generate_customer_data_correction_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "customer_data_correction")
    corrections = unique_records(
        _named(hints.get("corrections") or hints.get("fields"), ("field", "system")),
        [
            {
                "name": "customer data correction intake",
                "owner": "privacy_owner",
                "severity": "medium",
                "deadline": "not recorded",
            }
        ],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, correction_count=len(corrections)),
        "correction_items": [_item("CDC", index, item, "privacy_owner", evidence_ids) for index, item in enumerate(corrections, start=1)],
        "affected_systems": _section(hints, ("systems", "affected_systems"), "CDS", "system_owner", "Confirm affected system", evidence_ids, ["source of truth system"]),
        "correction_actions": _section(hints, ("correction_actions", "actions"), "CDA", "data_owner", "Perform correction action", evidence_ids, ["field correction workflow"]),
        "validation_checks": _section(hints, ("validation_checks", "validation_owners"), "CDV", "validation_owner", "Validate correction result", evidence_ids, ["before and after validation"]),
        "customer_notifications": _section(hints, ("customer_communications", "notifications"), "CDN", "customer_success_owner", "Notify customer", evidence_ids, ["customer correction notice"]),
        "audit_evidence": _section(hints, ("evidence", "audit_evidence"), "CDE", "compliance_owner", "Collect audit evidence", evidence_ids, ["correction audit trail"]),
        "evidence_references": ctx["evidence_references"],
    }


def _section(hints: dict[str, Any], keys: tuple[str, ...], prefix: str, owner: str, label: str, evidence_ids: list[str], fallback: list[Any]) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return [_item(prefix, index, item, owner, evidence_ids, label) for index, item in enumerate(unique_records(value, fallback), start=1)]


def _item(prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str], label: str = "Review customer data correction") -> dict[str, Any]:
    name = compact(item.get("name") or item.get("field") or item.get("system"))
    return row(prefix, index, name, compact(item.get("owner")) or owner, compact(item.get("description")) or compact(item.get("action")) or f"{label}: {name}.", evidence_ids, severity=compact(item.get("severity")) or "medium", status=compact(item.get("status") or item.get("deadline_status")) or "open", deadline=compact(item.get("deadline") or item.get("due")), field=compact(item.get("field")), system=compact(item.get("system")))


def _named(value: Any, aliases: tuple[str, ...]) -> Any:
    if not isinstance(value, list):
        return value
    result = []
    for item in value:
        if isinstance(item, dict) and not compact(item.get("name")):
            item = {**item, "name": next((compact(item.get(key)) for key in aliases if compact(item.get(key))), "")}
        result.append(item)
    return result
