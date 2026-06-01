from __future__ import annotations

import pytest

from max.spec.model_bias_assessment_plan import generate_model_bias_assessment_plan


def test_model_bias_assessment_plan_generates_required_workflow() -> None:
    plan = generate_model_bias_assessment_plan(_spec())

    assert plan["summary"]["model_name"] == "ranking-v2"
    assert set(plan) >= {"dataset_audit", "metric_thresholds", "subgroup_evaluation", "mitigation_workflow", "approval_gates"}
    assert [item["name"] for item in plan["dataset_audit"]] == ["golden eval", "shadow labels"]
    assert [item["threshold"] for item in plan["metric_thresholds"]] == [">= 0.8", "<= 3pp gap"]
    assert [item["protected_attribute"] for item in plan["subgroup_evaluation"]] == ["age", "gender"]
    assert plan["approval_gates"][-1]["deadline"] == "2026-09-15"


def test_model_bias_assessment_plan_is_deterministic() -> None:
    assert generate_model_bias_assessment_plan(_spec()) == generate_model_bias_assessment_plan(_spec())


@pytest.mark.parametrize(
    "field,match",
    [
        ("model_name", "model name"),
        ("target_users", "target users"),
        ("protected_attributes", "protected attributes"),
        ("evaluation_datasets", "evaluation datasets"),
        ("metrics", "metrics"),
    ],
)
def test_model_bias_assessment_plan_validates_required_inputs(field: str, match: str) -> None:
    hints = dict(_spec()["metadata"]["model_bias_assessment"])
    hints[field] = []

    with pytest.raises(ValueError, match=match):
        generate_model_bias_assessment_plan({"metadata": {"model_bias_assessment": hints}})


def _spec() -> dict:
    return {
        "metadata": {
            "model_bias_assessment": {
                "model_name": "ranking-v2",
                "target_users": ["job seekers", "recruiters"],
                "protected_attributes": ["gender", "age"],
                "evaluation_datasets": [{"name": "shadow labels"}, {"name": "golden eval"}],
                "metrics": [
                    {"metric": "false positive parity", "threshold": "<= 3pp gap"},
                    {"metric": "adverse impact ratio", "threshold": ">= 0.8"},
                ],
                "owners": ["ml owner", "rai owner"],
                "decision_deadline": "2026-09-15",
            }
        }
    }
