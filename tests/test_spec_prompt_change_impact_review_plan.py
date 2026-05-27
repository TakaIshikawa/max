from __future__ import annotations

from max.spec.prompt_change_impact_review_plan import generate_prompt_change_impact_review_plan


def test_prompt_change_impact_review_plan_reflects_metadata_hints() -> None:
    plan = generate_prompt_change_impact_review_plan({"metadata": {"prompt_change_impact_review": {"prompt_changes": [{"prompt": "ranking system", "before": "v1", "after": "v2", "stage": "scoring"}], "affected_workflows": ["recommendation ranking"], "evaluation_checks": ["golden replay"], "safety_privacy_review": ["PII review"], "rollout_gates": ["5% canary"], "monitoring_signals": ["conversion quality"]}}})

    assert set(plan) >= {"prompt_changes", "affected_workflows", "evaluation_checks", "safety_privacy_review", "rollout_gates", "monitoring_signals", "evidence_references"}
    assert plan["prompt_changes"][0]["before"] == "v1"
    assert plan["prompt_changes"][0]["after"] == "v2"
    assert plan["high_impact_changes"][0]["stage"] == "scoring"


def test_prompt_change_impact_review_plan_flags_spec_generation_high_impact() -> None:
    plan = generate_prompt_change_impact_review_plan({"metadata": {"prompt_change_impact_review": {"pipeline_stages": ["spec-generation"], "prompt_changes": [{"stage": "spec-generation"}]}}})

    assert plan["prompt_changes"][0]["impact_level"] == "high"
