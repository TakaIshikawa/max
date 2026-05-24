"""Generate deterministic vector index rebuild plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.vector_index_rebuild_plan.v1"
KIND = "max.spec.vector_index_rebuild_plan"


def generate_vector_index_rebuild_plan(spec_like: Any) -> dict[str, Any]:
    spec, ctx, metadata_hints, evidence_ids = base(spec_like, "vector_index_rebuild")
    hints = metadata_hints or (spec if isinstance(spec, dict) else {})
    indexes = unique_records(
        named(
            hints.get("indexes") or hints.get("embedding_indexes") or hints.get("affected_indexes"),
            ("index", "collection", "namespace"),
        ),
        [
            {
                "name": "primary embedding index",
                "index": "primary embedding index",
                "owner": "search_platform_owner",
                "severity": "high",
            }
        ],
    )
    owners = unique_records(
        named(hints.get("owners") or hints.get("owner_matrix") or hints.get("approvers"), ("role", "team")),
        [
            {"name": "search platform owner", "role": "rebuild lead", "team": "search_platform"},
            {"name": "data quality owner", "role": "validation approver", "team": "data_quality"},
        ],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "title": "Vector Index Rebuild Plan",
        "summary": source_summary(ctx, index_count=len(indexes), owner_count=len(owners)),
        "scope": [
            item(
                "VIR",
                index,
                record,
                "search_platform_owner",
                evidence_ids,
                "Rebuild affected embedding index",
                name_keys=("name", "index", "collection", "namespace"),
                extra_keys=("collection", "namespace", "environment"),
            )
            for index, record in enumerate(indexes, start=1)
        ],
        "rebuild_trigger": section(
            hints,
            ("rebuild_trigger", "trigger", "triggers"),
            "VIT",
            "program_owner",
            "Document vector index rebuild trigger",
            evidence_ids,
            ["embedding model change, source snapshot refresh, corruption, or retrieval drift"],
        ),
        "source_snapshot": section(
            hints,
            ("source_snapshot", "snapshot", "snapshots"),
            "VIS",
            "data_owner",
            "Freeze source snapshot for rebuild",
            evidence_ids,
            ["versioned source corpus, embedding model version, chunker config, and lineage manifest"],
            extra_keys=("snapshot_id", "corpus", "embedding_model", "chunker_version"),
        ),
        "rebuild_steps": section(
            hints,
            ("rebuild_steps", "steps", "workflow"),
            "VIB",
            "search_platform_owner",
            "Execute vector index rebuild step",
            evidence_ids,
            [
                "freeze writes, rebuild shadow index, backfill embeddings, compare retrieval quality, "
                "and atomically promote the rebuilt index"
            ],
        ),
        "validation_checks": section(
            hints,
            ("validation_checks", "validation", "thresholds", "validation_thresholds"),
            "VIV",
            "quality_owner",
            "Validate rebuilt vector index",
            evidence_ids,
            [
                "document count parity, embedding coverage >= 99.9%, recall parity within 1%, "
                "and zero critical retrieval regressions"
            ],
            extra_keys=("metric", "threshold", "query_set"),
        ),
        "rollback_plan": section(
            hints,
            ("rollback_plan", "rollback", "backout"),
            "VIX",
            "release_manager",
            "Rollback vector index promotion",
            evidence_ids,
            ["repoint traffic to the last healthy index alias and preserve rebuild artifacts for review"],
        ),
        "owners": [
            item(
                "VIO",
                index,
                record,
                "program_owner",
                evidence_ids,
                "Assign vector index rebuild owner",
                name_keys=("name", "role", "team"),
                extra_keys=("role", "team", "contact"),
            )
            for index, record in enumerate(owners, start=1)
        ],
        "timeline": section(
            hints,
            ("timeline", "milestones", "schedule"),
            "VIM",
            "program_owner",
            "Track vector index rebuild milestone",
            evidence_ids,
            ["snapshot freeze, shadow rebuild, validation, promotion, monitoring, and closure"],
        ),
        "risks": section(
            hints,
            ("risks", "risk_register", "known_risks"),
            "VIK",
            "program_owner",
            "Track vector index rebuild risk",
            evidence_ids,
            ["stale embeddings, recall regression, partial corpus coverage, alias cutover failure"],
        ),
        "acceptance_criteria": section(
            hints,
            ("acceptance_criteria", "acceptance", "evidence", "acceptance_evidence"),
            "VIA",
            "quality_owner",
            "Collect vector index rebuild acceptance evidence",
            evidence_ids,
            ["validation report, corpus parity query, rollback drill result, and owner signoff"],
        ),
        "evidence_references": ctx["evidence_references"],
    }
