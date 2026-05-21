"""Generate deterministic entitlement sunset exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records


SCHEMA_VERSION = "max.spec.entitlement_sunset_exception_plan.v1"
KIND = "max.spec.entitlement_sunset_exception_plan"


def generate_entitlement_sunset_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "entitlement_sunset_exception")
    exceptions = unique_records(
        hints.get("entitlements") or hints.get("exceptions"),
        [{"name": "legacy entitlement exception", "owner": "product_owner", "severity": "medium", "expiration": "not recorded"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, exception_count=len(exceptions)),
        "entitlement_exceptions": [_item("ESE", index, item, "product_owner", evidence_ids) for index, item in enumerate(exceptions, start=1)],
        "approval_gates": _section(hints, ("approval_owners", "approvals"), "ESA", "approval_owner", "Capture entitlement exception approval", evidence_ids, ["product and security approval"]),
        "customer_impact": _section(hints, ("affected_customers", "customers"), "ESC", "customer_success_owner", "Confirm affected customer impact", evidence_ids, ["affected customer inventory"]),
        "migration_paths": _section(hints, ("migration_paths", "migration"), "ESM", "migration_owner", "Track entitlement migration path", evidence_ids, ["replacement entitlement path"]),
        "kill_criteria": _section(hints, ("kill_criteria", "expiration_criteria"), "ESK", "product_owner", "Define entitlement kill criteria", evidence_ids, ["exception expiration review"]),
        "evidence_checks": _section(hints, ("evidence", "evidence_checks"), "ESEV", "compliance_owner", "Collect entitlement exception evidence", evidence_ids, ["approval and migration evidence"]),
        "evidence_references": ctx["evidence_references"],
    }


def _section(hints: dict[str, Any], keys: tuple[str, ...], prefix: str, owner: str, label: str, evidence_ids: list[str], fallback: list[Any]) -> list[dict[str, Any]]:
    value = next((hints[key] for key in keys if key in hints), None)
    return [_item(prefix, index, item, owner, evidence_ids, label) for index, item in enumerate(unique_records(value, fallback), start=1)]


def _item(prefix: str, index: int, item: dict[str, Any], owner: str, evidence_ids: list[str], label: str = "Review entitlement sunset exception") -> dict[str, Any]:
    name = compact(item.get("name"))
    return row(prefix, index, name, compact(item.get("owner")) or owner, compact(item.get("description")) or f"{label}: {name}.", evidence_ids, severity=compact(item.get("severity")) or "medium", status=compact(item.get("status")) or "open", expiration=compact(item.get("expiration") or item.get("expiry")) or None, customer=compact(item.get("customer")))
