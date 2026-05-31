from __future__ import annotations

import json

from max.spec.vector_index_rebuild_plan import generate_vector_index_rebuild_plan


def test_vector_index_rebuild_plan_covers_required_sections() -> None:
    plan = generate_vector_index_rebuild_plan(
        {
            "metadata": {
                "vector_index_rebuild": {
                    "embedding_indexes": [
                        {
                            "index": "insight-evidence-prod",
                            "collection": "insight_chunks",
                            "namespace": "prod",
                            "owner": "search_ops",
                        }
                    ],
                    "rebuild_trigger": ["embedding model v3 cutover"],
                    "source_snapshot": [{"snapshot_id": "snap-42", "corpus": "evidence lake"}],
                    "rebuild_steps": ["build shadow index and promote alias"],
                    "validation_thresholds": [{"metric": "recall@10", "threshold": ">= 0.97"}],
                    "rollback_plan": ["restore previous index alias"],
                    "owners": [{"name": "Search Ops", "role": "rebuild lead"}],
                    "timeline": ["complete before weekly dedupe run"],
                    "acceptance_evidence": ["validation report attached"],
                }
            },
            "evidence": {"signal_ids": ["vir-1"]},
        }
    )

    assert plan["title"] == "Vector Index Rebuild Plan"
    assert set(plan) >= {
        "summary",
        "scope",
        "rebuild_trigger",
        "source_snapshot",
        "rebuild_steps",
        "validation_checks",
        "rollback_plan",
        "risks",
        "acceptance_criteria",
    }
    assert plan["scope"][0]["name"] == "insight-evidence-prod"
    assert plan["scope"][0]["collection"] == "insight_chunks"
    assert plan["validation_checks"][0]["metric"] == "recall@10"
    assert plan["acceptance_criteria"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_vector_index_rebuild_plan_defaults_empty_input() -> None:
    plan = generate_vector_index_rebuild_plan({})

    assert plan["schema_version"] == "max.spec.vector_index_rebuild_plan.v1"
    assert plan["summary"]["index_count"] == 1
    assert plan["scope"][0]["name"] == "primary embedding index"
    assert plan["owners"][0]["role"] == "validation approver"
    assert plan["acceptance_criteria"][0]["name"] == (
        "validation report, corpus parity query, rollback drill result, and owner signoff"
    )


def test_vector_index_rebuild_plan_is_deterministic_and_accepts_raw_hints() -> None:
    payload = {"indexes": [{"index": "z-index"}, {"index": "a-index"}, {"index": "a-index"}]}

    assert generate_vector_index_rebuild_plan(payload) == generate_vector_index_rebuild_plan(payload)
    assert [item["name"] for item in generate_vector_index_rebuild_plan(payload)["scope"]] == [
        "a-index",
        "z-index",
    ]


def test_vector_index_rebuild_plan_flags_dimension_mismatch_and_stale_model() -> None:
    plan = generate_vector_index_rebuild_plan(
        {
            "metadata": {
                "vector_index_rebuild": {
                    "indexes": [
                        {
                            "index": "docs",
                            "current_dimension": 1536,
                            "target_dimension": 3072,
                            "current_model": "text-embedding-3-small",
                            "target_model": "text-embedding-3-large",
                        }
                    ],
                    "backfill_batches": [{"batch": "batch-001", "range": "0-1000"}],
                }
            }
        }
    )

    risk_names = [item["name"] for item in plan["risks"]]
    assert "dimension mismatch remediation" in risk_names
    assert "stale embedding model remediation" in risk_names
    assert plan["backfill_batches"][0]["name"] == "batch-001"
    assert "embedding_model_version" in plan
    assert "query_quality_checks" in plan
