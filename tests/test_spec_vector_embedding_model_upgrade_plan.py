from __future__ import annotations

import json

from max.spec.vector_embedding_model_upgrade_plan import generate_vector_embedding_model_upgrade_plan


def test_vector_embedding_model_upgrade_plan_covers_required_sections() -> None:
    plan = generate_vector_embedding_model_upgrade_plan(
        {
            "metadata": {
                "vector_embedding_model_upgrade": {
                    "current_model": "embed-v2",
                    "target_model": "embed-v3",
                    "indexes": [
                        {
                            "index": "docs-prod",
                            "collection": "docs",
                            "expected_dimensions": "3072",
                            "migration_window": "2026-06-01T02:00Z",
                        }
                    ],
                    "benchmark_datasets": [{"dataset": "support-search-gold", "metric": "recall@10"}],
                    "shadow_validation": [{"name": "10% shadow reads", "traffic_sample": "10%"}],
                    "cost_estimate_inputs": [{"documents": "10M", "tokens": "4B"}],
                    "rollback_criteria": [{"metric": "recall@10", "threshold": "drop > 1%"}],
                }
            }
        }
    )

    assert plan["title"] == "Vector Embedding Model Upgrade Plan"
    assert set(plan) >= {
        "current_model",
        "target_model",
        "compatibility_checks",
        "reindex_plan",
        "quality_checks",
        "shadow_validation",
        "cost_estimate_inputs",
        "rollback_criteria",
    }
    assert plan["current_model"] == "embed-v2"
    assert plan["target_model"] == "embed-v3"
    assert plan["reindex_plan"][0]["name"] == "docs-prod"
    assert plan["reindex_plan"][0]["expected_dimensions"] == "3072"
    assert plan["reindex_plan"][0]["migration_window"] == "2026-06-01T02:00Z"
    assert plan["quality_checks"][0]["dataset"] == "support-search-gold"
    assert plan["rollback_criteria"][0]["metric"] == "recall@10"


def test_vector_embedding_model_upgrade_plan_defaults_are_deterministic_and_json_safe() -> None:
    plan = generate_vector_embedding_model_upgrade_plan({})

    assert plan == generate_vector_embedding_model_upgrade_plan({})
    assert plan["schema_version"] == "max.spec.vector_embedding_model_upgrade_plan.v1"
    assert plan["current_model"] == "current embedding model"
    assert plan["target_model"] == "target embedding model"
    assert plan["reindex_plan"][0]["name"] == "primary retrieval index"
    assert json.loads(json.dumps(plan)) == plan
