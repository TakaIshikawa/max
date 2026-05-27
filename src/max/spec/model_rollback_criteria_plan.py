"""Generate deterministic model rollback criteria plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.model_rollback_criteria_plan.v1"
KIND = "max.spec.model_rollback_criteria_plan"


def generate_model_rollback_criteria_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_rollback_criteria")
    triggers = unique_records(named(hints.get("rollback_triggers") or hints.get("triggers"), ("trigger", "metric", "condition")), [{"name": "material evaluation regression", "severity": "high"}])
    thresholds = unique_records(named(hints.get("metric_thresholds") or hints.get("thresholds"), ("metric", "name")), [{"metric": "primary_eval_score", "threshold": "-0.03", "severity": "high"}])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, rollback_trigger_count=len(triggers), metric_threshold_count=len(thresholds)),
        "rollback_triggers": [item("MRT", index, record, "model_owner", evidence_ids, "Define rollback trigger", name_keys=("name", "trigger", "metric", "condition"), extra_keys=("trigger", "metric", "condition")) for index, record in enumerate(triggers, start=1)],
        "metric_thresholds": [item("MRM", index, record, "evaluation_owner", evidence_ids, "Set rollback metric threshold", name_keys=("name", "metric", "threshold"), extra_keys=("metric", "threshold", "window")) for index, record in enumerate(thresholds, start=1)],
        "approval_gates": section(hints, ("approval_gates", "approvals", "owner_approvals"), "MRA", "release_owner", "Approve rollback decision", evidence_ids, ["model owner, evaluation owner, incident commander, and customer success approval"]),
        "validation_evidence": section(hints, ("validation_evidence", "evidence", "validation"), "MRV", "evaluation_owner", "Collect rollback validation evidence", evidence_ids, ["baseline comparison, canary metrics, error analysis, and release notes"]),
        "customer_impact_checks": section(hints, ("customer_impact_checks", "customer_checks", "impact_checks"), "MRC", "customer_success_owner", "Assess customer impact before rollback", evidence_ids, ["affected tenants, active experiments, support escalations, and communication needs"]),
        "post_rollback_monitoring": section(hints, ("post_rollback_monitoring", "monitoring", "monitors"), "MRP", "model_owner", "Monitor after rollback", evidence_ids, ["quality, latency, cost, safety, and customer support signals for 48 hours"]),
        "evidence_references": ctx["evidence_references"],
    }
