"""Generate deterministic search relevance tuning plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary

SCHEMA_VERSION = "max.spec.search_relevance_tuning_plan.v1"
KIND = "max.spec.search_relevance_tuning_plan"


def generate_search_relevance_tuning_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "search_relevance_tuning")
    surface = compact(hints.get("surface") or hints.get("search_surface")) or ctx["workflow_context"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, search_surface=surface),
        "baseline": section(hints, ("baseline_metrics", "baseline"), "SRTB", "search_owner", "Capture relevance baseline", evidence_ids, ["nDCG, click-through rate, zero-result rate, reformulation rate"]),
        "target_queries": section(hints, ("target_queries", "queries"), "SRTQ", "product_owner", "Tune target query", evidence_ids, ["head queries", "tail queries", "no-result queries"]),
        "ranking_signals": section(hints, ("ranking_signals", "signals"), "SRTS", "search_owner", "Review ranking signal", evidence_ids, ["text match", "freshness", "popularity", "personalization eligibility"]),
        "experiment_design": section(hints, ("experiment_design", "experiment"), "SRTE", "experiment_owner", "Design relevance experiment", evidence_ids, ["offline eval, interleaving, A/B rollout, guardrail metrics"]),
        "evaluation_dataset": section(hints, ("evaluation_dataset", "dataset"), "SRTD", "quality_owner", "Prepare evaluation dataset", evidence_ids, ["judged queries with segment coverage and freshness metadata"]),
        "rollout_gates": section(hints, ("rollout_gates", "gates"), "SRTR", "release_owner", "Gate relevance rollout", evidence_ids, ["offline lift", "guardrails stable", "support feedback reviewed"]),
        "regression_monitoring": section(hints, ("regressions_to_monitor", "regression_monitoring"), "SRTM", "observability_owner", "Monitor relevance regression", evidence_ids, ["zero-result spike", "CTR drop", "latency increase", "complaint increase"]),
        "rollback": section(hints, ("rollback",), "SRTO", "on_call_owner", "Rollback relevance tuning", evidence_ids, ["restore previous ranking configuration and index weights"]),
        "owner_signoff": section(hints, ("owner_signoff", "signoff"), "SRTA", "program_owner", "Approve relevance tuning", evidence_ids, ["search, product, quality, and support signoff"]),
        "evidence_references": ctx["evidence_references"],
    }
