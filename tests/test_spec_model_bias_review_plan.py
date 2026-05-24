from __future__ import annotations

from max.spec.model_bias_review_plan import generate_model_bias_review_plan


def test_model_bias_review_plan_covers_review_workflow() -> None:
    plan = generate_model_bias_review_plan(
        {
            "profiles": [{"profile": "enterprise admins", "sample_size": 40}],
            "target_users": [{"target_user": "small business owner"}],
            "metrics": [{"metric": "false positive rate parity", "threshold": "<= 3pp gap"}],
            "review_rubric": ["score tone, factuality, and disparate recommendations"],
            "mitigations": ["hold release until parity gap is resolved"],
            "release_gate": ["responsible AI signoff required"],
        }
    )

    assert plan["title"] == "Model Bias Review Plan"
    assert set(plan) >= {
        "cohorts",
        "bias_hypotheses",
        "metrics",
        "review_rubric",
        "mitigation_actions",
        "escalation_criteria",
        "acceptance_gate",
    }
    assert plan["cohorts"][0]["profile"] == "enterprise admins"
    assert plan["metrics"][0]["metric"] == "false positive rate parity"
    assert plan["metrics"][0]["threshold"] == "<= 3pp gap"


def test_model_bias_review_plan_defaults_missing_metrics() -> None:
    plan = generate_model_bias_review_plan({})

    assert plan["schema_version"] == "max.spec.model_bias_review_plan.v1"
    assert plan["summary"]["metric_count"] == 1
    assert plan["metrics"][0]["metric"] == "quality parity"
    assert plan["acceptance_gate"][0]["name"] == (
        "all critical findings resolved, parity thresholds met, mitigations tracked, and approvers signed off"
    )


def test_model_bias_review_plan_is_deterministic_and_orders_inputs() -> None:
    payload = {"profiles": [{"profile": "zeta"}, {"profile": "alpha"}, {"profile": "alpha"}]}

    assert generate_model_bias_review_plan(payload) == generate_model_bias_review_plan(payload)
    assert [item["name"] for item in generate_model_bias_review_plan(payload)["cohorts"]] == [
        "alpha",
        "zeta",
    ]
