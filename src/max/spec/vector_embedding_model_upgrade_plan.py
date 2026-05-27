"""Generate deterministic vector embedding model upgrade plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.vector_embedding_model_upgrade_plan.v1"
KIND = "max.spec.vector_embedding_model_upgrade_plan"


def generate_vector_embedding_model_upgrade_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "vector_embedding_model_upgrade")
    indexes = unique_records(
        named(hints.get("indexes") or hints.get("index_names") or hints.get("affected_indexes"), ("index", "name")),
        [{"name": "primary retrieval index", "index": "primary retrieval index"}],
    )
    benchmarks = unique_records(
        named(hints.get("benchmark_datasets") or hints.get("benchmarks") or hints.get("datasets"), ("dataset", "benchmark")),
        [{"name": "retrieval quality benchmark", "dataset": "retrieval quality benchmark"}],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Vector Embedding Model Upgrade Plan",
        "summary": source_summary(ctx, index_count=len(indexes), benchmark_count=len(benchmarks)),
        "current_model": compact(hints.get("current_model") or hints.get("source_model")) or "current embedding model",
        "target_model": compact(hints.get("target_model") or hints.get("new_model")) or "target embedding model",
        "compatibility_checks": section(
            hints,
            ("compatibility_checks", "compatibility", "schema_checks"),
            "VEC",
            "search_platform_owner",
            "Check embedding model compatibility",
            evidence_ids,
            ["dimension parity or migration mapping, distance metric support, chunker compatibility, and metadata schema parity"],
            extra_keys=("expected_dimensions", "distance_metric", "collection"),
        ),
        "reindex_plan": [
            item(
                "VER",
                index,
                record,
                "search_platform_owner",
                evidence_ids,
                "Reindex embedding collection",
                name_keys=("name", "index", "collection"),
                extra_keys=("collection", "expected_dimensions", "migration_window"),
            )
            for index, record in enumerate(indexes, start=1)
        ],
        "quality_checks": [
            item(
                "VEQ",
                index,
                record,
                "evaluation_owner",
                evidence_ids,
                "Compare embedding quality benchmark",
                name_keys=("name", "dataset", "benchmark"),
                extra_keys=("dataset", "metric", "baseline", "target", "threshold"),
            )
            for index, record in enumerate(benchmarks, start=1)
        ],
        "shadow_validation": section(
            hints,
            ("shadow_validation", "shadow_read_validation", "shadow_reads"),
            "VES",
            "search_platform_owner",
            "Validate embedding model with shadow reads",
            evidence_ids,
            ["mirror production retrieval traffic, compare top-k overlap, latency, empty results, and safety filters"],
            extra_keys=("traffic_sample", "duration", "threshold"),
        ),
        "cost_estimate_inputs": section(
            hints,
            ("cost_estimate_inputs", "cost_inputs", "costs"),
            "VEK",
            "finance_owner",
            "Estimate embedding upgrade cost",
            evidence_ids,
            ["document count, token volume, embedding dimensions, storage growth, and rebuild compute"],
            extra_keys=("documents", "tokens", "storage_growth", "compute_hours"),
        ),
        "rollback_criteria": section(
            hints,
            ("rollback_criteria", "rollback", "backout"),
            "VEX",
            "release_manager",
            "Rollback embedding model upgrade",
            evidence_ids,
            ["recall regression beyond threshold, latency breach, cost overrun, or shadow-read mismatch"],
            extra_keys=("metric", "threshold", "owner_role"),
        ),
        "evidence_references": ctx["evidence_references"],
    }
