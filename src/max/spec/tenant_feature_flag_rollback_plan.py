"""Generate deterministic tenant feature flag rollback plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.tenant_feature_flag_rollback_plan.v1"
KIND = "max.spec.tenant_feature_flag_rollback_plan"


def generate_tenant_feature_flag_rollback_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "tenant_feature_flag_rollback")
    tenants = unique_records(named(hints.get("tenants") or hints.get("segments") or hints.get("tenant_segments"), ("tenant", "segment", "name")), [{"name": "tenant rollback inventory bootstrap", "risk": "unknown", "flag_owner": "missing"}])
    tenants = sorted(tenants, key=lambda row: (_risk(row), compact(row.get("name")).casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Tenant Feature Flag Rollback Plan", "summary": source_summary(ctx, tenant_group_count=len(tenants), high_risk_group_count=sum(1 for row in tenants if _risk(row) == 0)), "tenant_groups": [item("TFR", i, row, "flag_owner", evidence_ids, "Group tenant feature flag rollback", name_keys=("name", "tenant", "segment"), extra_keys=("risk", "flag_owner", "current_state", "target_state")) for i, row in enumerate(tenants, 1)], "blast_radius": section(hints, ("blast_radius", "impact"), "TFB", "product_owner", "Assess feature flag rollback blast radius", evidence_ids, ["tenant count, segment risk, active users, dependent workflows, and customer commitments"]), "flag_state_inventory": section(hints, ("flag_state_inventory", "flag_states"), "TFS", "flag_owner", "Inventory feature flag state", evidence_ids, ["flag key, current state, target state, default state, owner, and dependent services"]), "rollback_sequence": _sequence(tenants, evidence_ids), "validation_checks": section(hints, ("validation_checks", "validation"), "TFV", "qa_owner", "Validate tenant feature flag rollback", evidence_ids, ["confirm flag state, smoke affected workflows, compare metrics, and sample tenant logs"]), "customer_communication": section(hints, ("customer_communication", "communication"), "TFC", "customer_owner", "Communicate tenant feature flag rollback", evidence_ids, ["notify high-risk tenants, customer success, support, and status channels as needed"]), "risk_flags": _flags(tenants, evidence_ids), "evidence_references": ctx["evidence_references"]}


def _risk(row: dict[str, Any]) -> int:
    text = f"{compact(row.get('risk'))} {compact(row.get('segment'))} {compact(row.get('tenant'))} {compact(row.get('name'))}".lower()
    return 0 if any(term in text for term in ("critical", "high", "enterprise", "regulated")) else 1


def _sequence(tenants: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [item("TFO", i, {"name": compact(row.get("name")), "severity": "high" if _risk(row) == 0 else "medium", "description": "Rollback high-risk tenant segment first with owner approval and immediate validation." if _risk(row) == 0 else "Rollback tenant segment after high-risk groups and validate flag state."}, compact(row.get("flag_owner")) or "flag_owner", evidence_ids, "Sequence tenant feature flag rollback") for i, row in enumerate(tenants, 1)]


def _flags(tenants: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    flags = []
    for row in tenants:
        if not compact(row.get("flag_owner")) or compact(row.get("flag_owner")).lower() == "missing":
            flags.append(item("TFF", len(flags) + 1, {"name": compact(row.get("name")), "severity": "high", "description": "Missing flag owner blocks tenant rollback until ownership is assigned."}, "product_owner", evidence_ids, "Flag tenant rollback risk"))
    return flags or [item("TFF", 1, {"name": "tenant rollback owners assigned", "severity": "low"}, "flag_owner", evidence_ids, "Record tenant rollback readiness")]
