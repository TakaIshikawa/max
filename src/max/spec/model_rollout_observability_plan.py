"""Generate deterministic model rollout observability plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, row, source_summary

SCHEMA_VERSION = "max.spec.model_rollout_observability_plan.v1"
KIND = "max.spec.model_rollout_observability_plan"


def generate_model_rollout_observability_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "model_rollout_observability")
    model = compact(hints.get("model") or hints.get("model_name")) or "candidate model"
    version = compact(hints.get("version") or hints.get("model_version")) or "next"
    thresholds = hints.get("alert_thresholds") if isinstance(hints.get("alert_thresholds"), dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, model=model, version=version),
        "rollout_context": {"model": model, "version": version, "owner": compact(hints.get("owner")) or "ml_platform_owner"},
        "rollout_stages": section(hints, ("rollout_stages", "stages"), "MRS", "release_owner", "Observe model rollout stage", evidence_ids, ["shadow traffic", "1% canary", "25% canary", "100% rollout"]),
        "golden_signals": section(hints, ("golden_signals", "signals"), "MRG", "observability_owner", "Track model golden signal", evidence_ids, ["latency p95", "error rate", "quality score", "cost per request"]),
        "alert_thresholds": [
            row("MRA", index, name, "on_call_owner", f"Alert when {name} crosses {value}.", evidence_ids, threshold=value)
            for index, (name, value) in enumerate(sorted((thresholds or {"latency_p95_ms": 1200, "error_rate": 0.02, "quality_drop": 0.05}).items()), start=1)
        ],
        "dashboard_requirements": section(hints, ("dashboard_requirements", "dashboards"), "MRD", "observability_owner", "Create rollout dashboard", evidence_ids, ["traffic split, latency, errors, quality, cost, and rollback status"]),
        "evaluation_probes": section(hints, ("evaluation_probes", "probes"), "MRP", "quality_owner", "Run model evaluation probe", evidence_ids, ["golden prompt set", "safety regression probes", "customer journey probes"]),
        "rollback_criteria": section(hints, ("rollback_criteria", "rollback"), "MRB", "on_call_owner", "Rollback model rollout", evidence_ids, ["quality regression exceeds threshold", "error budget burn accelerates", "critical safety regression appears"]),
        "owner_signoff": section(hints, ("owner_signoff", "signoff"), "MRO", "program_owner", "Approve model rollout observability", evidence_ids, ["ml platform, product, quality, and on-call signoff"]),
        "evidence_references": ctx["evidence_references"],
    }
