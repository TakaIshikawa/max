"""Generate deterministic schema contract migration plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary

SCHEMA_VERSION = "max.spec.schema_contract_migration_plan.v1"
KIND = "max.spec.schema_contract_migration_plan"


def generate_schema_contract_migration_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "schema_contract_migration")
    current = compact(hints.get("current_contract")) or "current schema contract"
    target = compact(hints.get("target_contract")) or "target schema contract"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, current_contract=current, target_contract=target),
        "current_contract": {"name": current, "owner": compact(hints.get("owner")) or "data_platform_owner"},
        "target_contract": {"name": target, "compatibility_mode": compact(hints.get("compatibility_mode")) or "backward-compatible when possible"},
        "compatibility_risks": section(hints, ("compatibility_risks", "risks"), "SCM", "data_platform_owner", "Mitigate schema compatibility risk", evidence_ids, ["unknown consumer compatibility", "required field changes", "historical replay mismatch"]),
        "migration_steps": section(hints, ("migration_steps", "steps"), "SCS", "engineering_owner", "Migrate schema contract", evidence_ids, ["publish target contract", "dual-write or adapter shim", "consumer validation", "remove legacy path"]),
        "consumer_validation": section(hints, ("consumer_validation", "consumers"), "SCV", "consumer_owner", "Validate schema consumer", evidence_ids, ["contract tests for all known consumers"]),
        "rollout_sequencing": section(hints, ("rollout_sequencing", "rollout"), "SCR", "release_owner", "Sequence schema rollout", evidence_ids, ["dev", "staging", "canary producers", "full rollout"]),
        "rollback_strategy": section(hints, ("rollback_strategy", "rollback"), "SCB", "on_call_owner", "Rollback schema migration", evidence_ids, ["retain legacy schema writer and replay-safe downgrade path"]),
        "acceptance_checks": section(hints, ("acceptance_checks", "checks"), "SCA", "qa_owner", "Accept schema migration", evidence_ids, ["contract tests pass", "consumer lag stable", "no parse failures"]),
        "evidence_references": ctx["evidence_references"],
    }
