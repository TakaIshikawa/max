"""Generate deterministic support tier migration plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary, unique_records, values


SCHEMA_VERSION = "max.spec.support_tier_migration_plan.v1"
KIND = "max.spec.support_tier_migration_plan"


def generate_support_tier_migration_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "support_tier_migration")
    tiers = unique_records(
        hints.get("tier_changes") or hints.get("affected_tiers") or hints.get("tiers"),
        [
            {
                "name": "standard support tier update",
                "owner": "support_owner",
                "description": "Confirm source and target support tier handling.",
            }
        ],
    )
    customers = values(
        hints.get("impacted_customers") or hints.get("customer_segments") or hints.get("segments"),
        [ctx["target_user"]],
    )
    routing = unique_records(
        hints.get("routing_updates") or hints.get("support_routing_updates"),
        [
            {
                "name": "queue routing update",
                "owner": "support_operations_owner",
                "description": "Route migrated customers to the correct support queue.",
            }
        ],
    )
    entitlement = unique_records(
        hints.get("entitlement_checks"),
        [
            {
                "name": "entitlement parity check",
                "owner": "support_owner",
                "description": "Validate support entitlements after migration.",
            }
        ],
    )
    staffing = unique_records(
        hints.get("staffing_actions") or hints.get("staffing_impacts"),
        [
            {
                "name": "coverage readiness",
                "owner": "support_manager",
                "description": "Confirm staffing coverage for migrated tier volume.",
            }
        ],
    )
    communications = unique_records(
        hints.get("communications") or hints.get("customer_notices"),
        [
            {
                "name": "support tier notice",
                "owner": "customer_success_owner",
                "description": "Notify affected customers of tier and routing changes.",
            }
        ],
    )
    checks = unique_records(
        hints.get("validation_checks"),
        [
            {
                "name": "support migration validation",
                "owner": "support_owner",
                "description": "Validate tiers, routing, entitlement, staffing, and notices.",
            }
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(
            ctx, tier_change_count=len(tiers), impacted_customer_count=len(customers)
        ),
        "tier_changes": [
            _item("TIER", index, item, "support_owner", evidence_ids)
            for index, item in enumerate(tiers, start=1)
        ],
        "impacted_customers": [
            _named("CUST", index, customer, "customer_success_owner", evidence_ids)
            for index, customer in enumerate(customers, start=1)
        ],
        "routing_updates": [
            _item("ROUTE", index, item, "support_operations_owner", evidence_ids)
            for index, item in enumerate(routing, start=1)
        ],
        "entitlement_checks": [
            _item("ENT", index, item, "support_owner", evidence_ids)
            for index, item in enumerate(entitlement, start=1)
        ],
        "staffing_actions": [
            _item("STAFF", index, item, "support_manager", evidence_ids)
            for index, item in enumerate(staffing, start=1)
        ],
        "communications": [
            _item("COM", index, item, "customer_success_owner", evidence_ids)
            for index, item in enumerate(communications, start=1)
        ],
        "validation_checks": [
            _item("VC", index, item, "support_owner", evidence_ids)
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
        due=item.get("due") or item.get("deadline"),
    )
