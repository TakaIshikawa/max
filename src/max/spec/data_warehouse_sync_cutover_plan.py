"""Generate deterministic data warehouse sync cutover plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.data_warehouse_sync_cutover_plan.v1"
KIND = "max.spec.data_warehouse_sync_cutover_plan"


def generate_data_warehouse_sync_cutover_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "data_warehouse_sync_cutover")
    risks = unique_records(
        named(hints.get("risks") or hints.get("schema_risks") or hints.get("destination_risks"), ("schema", "destination", "source")),
        [{"name": "warehouse sync cutover risk", "owner": "analytics_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, risk_count=len(risks)),
        "sync_scope": section(hints, ("sync_scope", "scope"), "DWS", "analytics_owner", "Confirm warehouse sync scope", evidence_ids, ["source and destination sync job scope"]),
        "source_destination_systems": section(hints, ("systems", "source_destination_systems", "destinations"), "DWD", "data_platform_owner", "Inventory source and destination", evidence_ids, ["source system, destination warehouse, and sync job inventory"], extra_keys=("source", "destination")),
        "schema_destination_risks": [
            item("DWR", index, record, "analytics_owner", evidence_ids, "Resolve warehouse sync risk", name_keys=("name", "schema", "destination", "source"), extra_keys=("schema", "destination", "source", "impact"))
            for index, record in enumerate(risks, start=1)
        ],
        "compatibility_checks": section(hints, ("compatibility", "schema_compatibility"), "DWC", "data_platform_owner", "Run schema compatibility check", evidence_ids, ["schema, type, partition, and destination compatibility"]),
        "dual_run_validation": section(hints, ("dual_run", "dual_run_validation"), "DWV", "qa_owner", "Validate dual-run sync", evidence_ids, ["row counts, checksums, freshness, and sample query comparison"]),
        "lag_monitoring": section(hints, ("lag", "lag_monitoring", "monitoring"), "DWM", "on_call_owner", "Monitor warehouse sync lag", evidence_ids, ["lag threshold and freshness alert"]),
        "stakeholder_impact": section(hints, ("impact", "stakeholder_impact"), "DWI", "analytics_owner", "Assess stakeholder impact", evidence_ids, ["dashboard, data consumer, and downstream model impact"]),
        "cutover_steps": section(hints, ("cutover", "cutover_steps"), "DWX", "release_manager", "Execute warehouse sync cutover", evidence_ids, ["freeze, switch, validate, and notify steps"]),
        "rollback_replay": section(hints, ("rollback", "replay", "rollback_replay"), "DWB", "data_platform_owner", "Rollback or replay warehouse sync", evidence_ids, ["restore prior sync destination and replay missed events"]),
        "evidence_references": ctx["evidence_references"],
    }
