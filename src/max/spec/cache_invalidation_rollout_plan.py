"""Generate deterministic cache invalidation rollout plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary

SCHEMA_VERSION = "max.spec.cache_invalidation_rollout_plan.v1"
KIND = "max.spec.cache_invalidation_rollout_plan"


def generate_cache_invalidation_rollout_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "cache_invalidation_rollout")
    strategy = compact(hints.get("strategy") or hints.get("invalidation_strategy")) or "namespace version bump"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, invalidation_strategy=strategy),
        "cache_inventory": section(hints, ("cache_layers", "layers", "cache_inventory"), "CII", "platform_owner", "Review cache layer", evidence_ids, ["edge cache", "application cache", "database result cache"]),
        "invalidation_steps": section(hints, ("keys", "namespaces", "invalidation_steps"), "CIS", "engineering_owner", "Invalidate cache target", evidence_ids, ["identify namespace", "publish invalidation", "confirm miss and refill behavior"]),
        "warmup": section(hints, ("warmup", "warmup_steps"), "CIW", "release_owner", "Warm cache after invalidation", evidence_ids, ["preload top traffic keys and critical customer journeys"]),
        "blast_radius": section(hints, ("blast_radius",), "CIB", "program_owner", "Limit invalidation blast radius", evidence_ids, ["segment by namespace, tenant, region, or traffic cohort"]),
        "observability": section(hints, ("observability", "monitoring"), "CIO", "observability_owner", "Monitor cache invalidation", evidence_ids, ["hit rate, origin load, latency, errors, saturation"]),
        "rollback": section(hints, ("rollback",), "CIR", "on_call_owner", "Rollback cache invalidation", evidence_ids, ["restore previous namespace version or disable invalidation publisher"]),
        "post_rollout_validation": section(hints, ("post_rollout_validation", "validation"), "CIV", "qa_owner", "Validate cache rollout", evidence_ids, ["stale data cleared, hit rate recovered, no origin overload"]),
        "evidence_references": ctx["evidence_references"],
    }
