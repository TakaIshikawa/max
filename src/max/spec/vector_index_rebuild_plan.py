"""Generate deterministic vector index rebuild plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact
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
    batches = unique_records(
        named(hints.get("backfill_batches") or hints.get("batches") or hints.get("batch_plan"), ("batch", "range", "name")),
        [{"name": "no batch data supplied", "description": "Create deterministic backfill batches from the frozen source snapshot before rebuild."}],
    )
    risk_actions = _risk_actions(indexes, hints, evidence_ids)
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
        "embedding_model_version": section(
            hints,
            ("embedding_model_version", "embedding_model", "model_version"),
            "VIE",
            "search_platform_owner",
            "Pin embedding model version",
            evidence_ids,
            ["record current and target embedding model versions, output dimension, provider, and tokenizer config"],
            extra_keys=("current_model", "target_model", "current_dimension", "target_dimension", "model_version"),
        ),
        "backfill_batches": [
            item(
                "VIF",
                index,
                record,
                "data_owner",
                evidence_ids,
                "Backfill vector index batch",
                name_keys=("name", "batch", "range", "description"),
                extra_keys=("range", "batch_size", "status"),
            )
            for index, record in enumerate(batches, start=1)
        ],
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
        )
        + risk_actions,
        "query_quality_checks": section(
            hints,
            ("query_quality_checks", "quality_checks", "query_checks"),
            "VIQ",
            "quality_owner",
            "Run vector query quality check",
            evidence_ids,
            ["compare recall, precision, latency, and known-answer queries against the previous production index"],
            extra_keys=("metric", "threshold", "query_set"),
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


def _risk_actions(indexes: list[dict[str, Any]], hints: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    records = indexes + ([hints] if hints else [])
    if any(_dimension_mismatch(record) for record in records):
        actions.append(
            item(
                "VIK",
                100,
                {
                    "name": "dimension mismatch remediation",
                    "severity": "critical",
                    "description": "Block cutover until index schema dimension, embedding output dimension, and query encoder dimension match.",
                },
                "search_platform_owner",
                evidence_ids,
                "Track vector index rebuild risk",
            )
        )
    if any(_stale_model(record) for record in records):
        actions.append(
            item(
                "VIK",
                101,
                {
                    "name": "stale embedding model remediation",
                    "severity": "high",
                    "description": "Re-embed stale model-version batches before validation and record current target model in rebuild evidence.",
                },
                "search_platform_owner",
                evidence_ids,
                "Track vector index rebuild risk",
            )
        )
    return actions


def _dimension_mismatch(record: dict[str, Any]) -> bool:
    current = record.get("current_dimension") or record.get("source_dimension") or record.get("index_dimension")
    target = record.get("target_dimension") or record.get("embedding_dimension") or record.get("model_dimension")
    return bool(current and target and str(current) != str(target)) or bool(record.get("dimension_mismatch"))


def _stale_model(record: dict[str, Any]) -> bool:
    status = str(record.get("model_status") or record.get("embedding_model_status") or "").lower()
    current = compact(record.get("current_model") or record.get("current_model_version"))
    target = compact(record.get("target_model") or record.get("target_model_version"))
    return "stale" in status or bool(current and target and current != target)
