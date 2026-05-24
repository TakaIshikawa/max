from __future__ import annotations

import json

from max.spec import generate_model_evaluation_holdout_plan


def test_model_evaluation_holdout_plan_covers_controls_and_reporting() -> None:
    plan = generate_model_evaluation_holdout_plan(
        _spec(
            "model_evaluation_holdout",
            {
                "holdout_datasets": [
                    {
                        "dataset": "support-edge-cases",
                        "source": "labeled tickets",
                        "owner": "eval_owner",
                        "cadence": "quarterly",
                    }
                ],
                "evaluation_dimensions": [
                    {
                        "dimension": "toxicity",
                        "threshold": "0 critical failures",
                        "owner": "safety_owner",
                        "cadence": "per release",
                    }
                ],
                "leakage_controls": ["deny training jobs access"],
                "refresh_cadence": [{"name": "quarterly refresh", "cadence": "quarterly"}],
                "access_review": ["security and privacy recertification"],
                "pass_fail_thresholds": [
                    {"dimension": "toxicity", "threshold": "0 critical failures"}
                ],
                "reporting_plan": ["release gate evidence bundle"],
            },
        )
    )

    assert set(plan) >= {
        "holdout_datasets",
        "evaluation_dimensions",
        "leakage_controls",
        "refresh_cadence",
        "access_review",
        "pass_fail_thresholds",
        "reporting_plan",
        "evidence_references",
    }
    assert plan["holdout_datasets"][0]["dataset"] == "support-edge-cases"
    assert plan["holdout_datasets"][0]["owner"] == "eval_owner"
    assert plan["holdout_datasets"][0]["cadence"] == "quarterly"
    assert plan["evaluation_dimensions"][0]["dimension"] == "toxicity"
    assert plan["evaluation_dimensions"][0]["threshold"] == "0 critical failures"
    assert plan["evaluation_dimensions"][0]["owner"] == "safety_owner"
    assert json.loads(json.dumps(plan)) == plan


def test_model_evaluation_holdout_plan_defaults_practical_sections() -> None:
    plan = generate_model_evaluation_holdout_plan({})

    assert plan["schema_version"] == "max.spec.model_evaluation_holdout_plan.v1"
    assert plan["holdout_datasets"][0]["dataset"] == "golden holdout dataset"
    assert plan["evaluation_dimensions"][0]["threshold"] == "no material regression"
    assert plan["pass_fail_thresholds"][0]["name"] == (
        "quality above baseline, safety failures at zero criticals, and no "
        "protected-segment regression"
    )


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"signal_ids": ["meh-1"]}}
