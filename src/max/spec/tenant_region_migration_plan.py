"""Generate deterministic tenant region migration plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.tenant_region_migration_plan.v1"
KIND = "max.spec.tenant_region_migration_plan"


def generate_tenant_region_migration_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "tenant_region_migration")
    tenants = unique_records(
        named(hints.get("tenants") or hints.get("tenant_scope") or hints.get("migrations"), ("tenant", "account", "source_region", "target_region")),
        [{"name": "tenant region migration", "owner": "migration_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, tenant_count=len(tenants)),
        "migration_scope": [
            item(
                "TRM",
                index,
                record,
                "migration_owner",
                evidence_ids,
                "Migrate tenant region",
                name_keys=("name", "tenant", "account", "source_region", "target_region"),
                extra_keys=("tenant", "account", "source_region", "target_region"),
            )
            for index, record in enumerate(tenants, start=1)
        ],
        "region_scope": section(hints, ("regions", "region_scope", "source_target_regions"), "TRR", "migration_owner", "Confirm source and target region", evidence_ids, ["source region and target region"], extra_keys=("source_region", "target_region")),
        "tenant_eligibility": section(hints, ("eligibility", "tenant_eligibility", "eligible_tenants"), "TRE", "customer_owner", "Confirm tenant eligibility", evidence_ids, ["tenant eligibility, blockers, and consent state"], extra_keys=("tenant", "account", "status")),
        "data_replication_plan": section(hints, ("replication", "data_replication_plan", "replication_steps"), "TRD", "engineering_owner", "Execute data replication step", evidence_ids, ["snapshot, replicate, checksum, and freeze delta sync"]),
        "downtime_window": section(hints, ("downtime", "downtime_window", "maintenance_window"), "TRW", "operations_owner", "Confirm downtime window", evidence_ids, ["downtime window not recorded"], extra_keys=("window", "start", "end")),
        "compliance_checks": section(hints, ("compliance", "compliance_checks", "controls"), "TRC", "compliance_owner", "Complete compliance check", evidence_ids, ["residency, subprocessor, DPA, and audit logging check"]),
        "customer_communication": section(hints, ("communication", "customer_communication", "communications"), "TRN", "customer_owner", "Send customer communication", evidence_ids, ["customer notice, support path, and migration timing confirmation"]),
        "rollback": section(hints, ("rollback", "rollback_plan", "backout"), "TRB", "engineering_owner", "Rollback tenant migration", evidence_ids, ["restore source region routing and reconcile replicated writes"]),
        "post_migration_validation": section(hints, ("validation", "post_migration_validation", "validations"), "TRV", "engineering_owner", "Validate migrated tenant", evidence_ids, ["routing, data parity, latency, permissions, and customer acceptance validation"]),
        "evidence_references": ctx["evidence_references"],
    }
