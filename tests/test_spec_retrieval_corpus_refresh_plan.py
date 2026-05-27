from __future__ import annotations

from max.spec.retrieval_corpus_refresh_plan import generate_retrieval_corpus_refresh_plan


def test_retrieval_corpus_refresh_plan_normalizes_inputs() -> None:
    plan = generate_retrieval_corpus_refresh_plan(
        {
            "metadata": {
                "retrieval_corpus_refresh": {
                    "sources": ["docs", {"name": "support-kb"}, "docs"],
                    "stale_documents": ["pricing FAQ", "security page"],
                    "embedding_index": "prod-rag-v4",
                    "owners": ["search", "docs"],
                    "validation_samples": ["billing query"],
                }
            }
        }
    )

    assert [row["source"] for row in plan["corpus_inventory"]] == ["docs", "support-kb"]
    assert plan["corpus_inventory"][0]["embedding_index"] == "prod-rag-v4"
    assert [row["trigger"] for row in plan["staleness_triggers"]] == ["pricing FAQ", "security page"]
    assert plan["validation_checks"][0]["sample"] == "billing query"
    assert {row["stage"] for row in plan["rollout_plan"]} == {"shadow", "limited", "general"}
    assert plan["rollback_criteria"][0]["action"].startswith("Restore prior corpus")
    assert [row["owner"] for row in plan["stakeholder_signoff"]] == ["search", "docs"]


def test_retrieval_corpus_refresh_plan_has_sparse_defaults() -> None:
    plan = generate_retrieval_corpus_refresh_plan({})

    assert plan["summary"]["source_count"] == 1
    assert plan["corpus_inventory"][0]["source"] == "primary knowledge corpus"
    assert plan["refresh_steps"][1]["action"] == "Re-ingest changed documents and rebuild embeddings for primary embedding index."
    assert len(plan["validation_checks"]) == 2
