"""Generate deterministic retrieval corpus refresh plans."""

from __future__ import annotations

from typing import Any, Mapping

from max.spec._planning_common import compact, context, string_list, summary


SCHEMA_VERSION = "max.spec.retrieval_corpus_refresh_plan.v1"
KIND = "max.spec.retrieval_corpus_refresh_plan"


def generate_retrieval_corpus_refresh_plan(payload: Any) -> dict[str, Any]:
    spec = payload if isinstance(payload, dict) else {}
    ctx = context(spec)
    hints = _hints(spec)
    sources = _sources(hints)
    stale_documents = _list(hints.get("stale_documents")) or ["documents older than freshness SLA"]
    owners = _ordered(string_list(hints.get("owners")) or ["search_owner", "content_owner"])
    index = compact(hints.get("embedding_index")) or compact(hints.get("index")) or "primary embedding index"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": summary(ctx, source_count=len(sources), stale_document_count=len(stale_documents), embedding_index=index),
        "corpus_inventory": [
            {
                "id": f"SRC{idx}",
                "source": source,
                "owner": owners[min(idx - 1, len(owners) - 1)],
                "embedding_index": index,
                "refresh_scope": "full" if stale_documents else "incremental",
            }
            for idx, source in enumerate(sources, start=1)
        ],
        "staleness_triggers": [
            {"id": f"STL{idx}", "trigger": item, "owner": "content_owner", "action": "Include in refresh candidate set."}
            for idx, item in enumerate(stale_documents, start=1)
        ],
        "refresh_steps": [
            {"id": "REF1", "owner": "content_owner", "action": "Freeze source inventory and capture document counts before refresh."},
            {"id": "REF2", "owner": "search_owner", "action": f"Re-ingest changed documents and rebuild embeddings for {index}."},
            {"id": "REF3", "owner": "release_owner", "action": "Promote refreshed corpus through staged rollout with query shadowing."},
        ],
        "validation_checks": _validation_checks(hints),
        "rollout_plan": [
            {"id": "ROL1", "stage": "shadow", "traffic_percent": 0, "owner": "search_owner"},
            {"id": "ROL2", "stage": "limited", "traffic_percent": 10, "owner": "release_owner"},
            {"id": "ROL3", "stage": "general", "traffic_percent": 100, "owner": "release_owner"},
        ],
        "rollback_criteria": [
            {"id": "RB1", "owner": "search_owner", "condition": "retrieval precision, latency, or answer quality regresses", "action": "Restore prior corpus snapshot and embedding index alias."},
            {"id": "RB2", "owner": "content_owner", "condition": "source reconciliation or freshness validation fails", "action": "Stop rollout and repair source inventory."},
        ],
        "stakeholder_signoff": [
            {"id": f"SGN{idx}", "owner": owner, "required": True, "signoff": "Approve corpus refresh readiness and rollback evidence."}
            for idx, owner in enumerate(owners, start=1)
        ],
        "evidence_references": ctx["evidence_references"],
    }


def _hints(spec: dict[str, Any]) -> Mapping[str, Any]:
    metadata = spec.get("metadata") if isinstance(spec.get("metadata"), Mapping) else {}
    refresh = metadata.get("retrieval_corpus_refresh") if isinstance(metadata.get("retrieval_corpus_refresh"), Mapping) else {}
    return refresh or metadata or spec


def _sources(hints: Mapping[str, Any]) -> list[str]:
    return _list(hints.get("sources")) or _list(hints.get("source_inventory")) or ["primary knowledge corpus"]


def _validation_checks(hints: Mapping[str, Any]) -> list[dict[str, Any]]:
    samples = _list(hints.get("validation_samples")) or ["top production queries", "known-answer regression set"]
    return [
        {"id": f"VAL{idx}", "sample": sample, "owner": "quality_owner", "action": "Compare retrieved passages, citation freshness, latency, and answer quality against baseline."}
        for idx, sample in enumerate(samples, start=1)
    ]


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _ordered([compact(item.get("name") if isinstance(item, Mapping) else item) for item in value])
    text = compact(value)
    return [text] if text else []


def _ordered(values: list[str]) -> list[str]:
    return list(dict.fromkeys(compact(value) for value in values if compact(value)))
