from __future__ import annotations

from max.spec.model_evaluation_plan import generate_model_evaluation_plan


def test_model_evaluation_plan_covers_required_sections_and_strict_gates() -> None:
    plan = generate_model_evaluation_plan(
        {
            "project": {"title": "Recommendation Ranker"},
            "model": {
                "use_cases": ["user-facing recommendations"],
                "datasets": ["holdout-v1", "shadow-prod"],
                "metrics": ["ndcg", "precision"],
                "baselines": ["rules engine"],
            },
            "evidence": {"signal_ids": ["eval-1"]},
        }
    )

    assert plan["kind"] == "max.model_evaluation_plan"
    assert plan["summary"]["gate_level"] == "strict"
    assert plan["summary"]["regression_cadence"] == "per release"
    assert plan["datasets"] == ["holdout-v1", "shadow-prod"]
    assert plan["metrics"] == ["ndcg", "precision"]
    assert plan["acceptance_thresholds"]["critical_failure_rate"] == "0"
    assert plan["evidence"] == ["signal:eval-1"]


def test_model_evaluation_plan_defaults_missing_inputs() -> None:
    plan = generate_model_evaluation_plan({})

    assert plan["summary"]["title"] == "Unknown"
    assert plan["summary"]["gate_level"] == "standard"
    assert plan["datasets"] == ["Unknown"]
    assert plan["regression_cadence"] == "monthly"


def test_model_evaluation_plan_is_deterministic() -> None:
    payload = {"model": {"datasets": ["z", "a", "z"]}}

    assert generate_model_evaluation_plan(payload) == generate_model_evaluation_plan(payload)
    assert generate_model_evaluation_plan(payload)["datasets"] == ["a", "z"]
