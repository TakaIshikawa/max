from __future__ import annotations

from max.spec import generate_model_rollout_observability_plan


def test_model_rollout_observability_plan_preserves_model_metadata_and_thresholds() -> None:
    plan = generate_model_rollout_observability_plan({"metadata": {"model_rollout_observability": {"model": "ranker", "version": "v3", "alert_thresholds": {"quality_drop": 0.03}, "evaluation_probes": ["golden set"]}}})

    assert plan["summary"]["model"] == "ranker"
    assert plan["rollout_context"]["version"] == "v3"
    assert plan["alert_thresholds"][0]["threshold"] == 0.03
    assert plan["evaluation_probes"][0]["name"] == "golden set"


def test_model_rollout_observability_plan_has_sparse_defaults() -> None:
    plan = generate_model_rollout_observability_plan({})

    assert plan["golden_signals"]
    assert plan["alert_thresholds"]
    assert plan["rollback_criteria"]
