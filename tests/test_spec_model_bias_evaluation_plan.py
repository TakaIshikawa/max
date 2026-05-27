from __future__ import annotations

import json

from max.spec.model_bias_evaluation_plan import generate_model_bias_evaluation_plan


def test_model_bias_evaluation_plan_covers_required_sections() -> None:
    plan = generate_model_bias_evaluation_plan(
        {
            "metadata": {
                "model_bias_evaluation": {
                    "model": "claims-risk-v2",
                    "user_facing": "yes",
                    "protected_segments": [
                        {"segment": "age_65_plus", "attribute": "age", "sample_size": "300"}
                    ],
                    "slice_metrics": [{"metric": "false_negative_rate_delta", "baseline": "0.03"}],
                    "remediation_actions": [{"name": "raise review threshold", "owner": "model_risk"}],
                    "approval_gates": [{"approver": "Model Risk Lead", "decision": "approve"}],
                }
            },
            "evidence": {"signal_ids": ["bias-eval-9"]},
        }
    )

    assert plan["title"] == "Model Bias Evaluation Plan"
    assert plan["threshold_mode"] == "strict"
    assert plan["minimum_sample_size"] == 250
    assert plan["protected_segments"][0]["segment"] == "age_65_plus"
    assert plan["slice_metrics"][0]["metric"] == "false_negative_rate_delta"
    assert plan["thresholds"][0]["threshold"] == ">= 0.90"
    assert plan["remediation_actions"][0]["owner"] == "model_risk"
    assert plan["approval_gates"][0]["approver"] == "Model Risk Lead"
    assert plan["blockers"] == []
    assert plan["protected_segments"][0]["evidence_reference_ids"] == ["EV1"]


def test_model_bias_evaluation_missing_inputs_create_blockers() -> None:
    plan = generate_model_bias_evaluation_plan({"metadata": {"model_bias_evaluation": {}}})

    assert [blocker["name"] for blocker in plan["blockers"]] == [
        "missing protected segments",
        "missing remediation owner",
    ]
    assert plan["summary"]["blocker_count"] == 2


def test_model_bias_evaluation_warns_for_small_samples_and_stale_evidence() -> None:
    plan = generate_model_bias_evaluation_plan(
        {
            "metadata": {
                "model_bias_evaluation": {
                    "protected_segments": [{"segment": "locale_ja", "sample_size": "75"}],
                    "remediation_owner": "model_owner",
                    "evaluation_evidence": {"status": "stale", "run_id": "eval-1"},
                }
            }
        }
    )

    assert [warning["name"] for warning in plan["warnings"]] == [
        "small sample size for locale_ja",
        "stale evaluation evidence",
    ]
    assert plan["warnings"][0]["minimum_sample_size"] == 100
    assert plan["summary"]["warning_count"] == 2


def test_model_bias_evaluation_defaults_are_deterministic_and_json_safe() -> None:
    plan = generate_model_bias_evaluation_plan({})

    assert plan == generate_model_bias_evaluation_plan({})
    assert plan["schema_version"] == "max.spec.model_bias_evaluation_plan.v1"
    assert plan["summary"]["protected_segment_count"] == 0
    assert plan["threshold_mode"] == "standard"
    assert plan["thresholds"][0]["threshold"] == ">= 0.80"
    assert json.loads(json.dumps(plan)) == plan
