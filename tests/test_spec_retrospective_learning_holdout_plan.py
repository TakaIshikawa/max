from __future__ import annotations

import json

from max.spec import generate_retrospective_learning_holdout_plan


def test_retrospective_learning_holdout_plan_normalizes_percentage_and_sections() -> None:
    plan = generate_retrospective_learning_holdout_plan(
        _spec(
            {
                "holdout_percentage": 0.2,
                "cohorts": [{"cohort": "support feedback", "profile": "enterprise", "owner": "eval_owner"}],
                "metrics": [{"metric": "precision lift", "threshold": ">= 3%"}],
                "timeline": [{"name": "two release cycles", "duration": "60 days"}],
                "guardrails": ["exclude safety escalations"],
                "analysis_steps": ["compare against retained outcomes"],
                "reintegration_criteria": ["reviewer signoff"],
            }
        )
    )

    assert plan["summary"]["holdout_percentage"] == 20
    assert plan["holdout_cohorts"][0]["holdout_percentage"] == "20"
    assert plan["holdout_cohorts"][0]["profile"] == "enterprise"
    assert plan["success_metrics"][0]["threshold"] == ">= 3%"
    assert set(plan) >= {
        "holdout_cohorts",
        "timeline",
        "success_metrics",
        "guardrails",
        "analysis_steps",
        "reintegration_criteria",
    }
    assert json.loads(json.dumps(plan)) == plan


def test_retrospective_learning_holdout_plan_bounds_percentage_and_is_deterministic() -> None:
    payload = _spec({"percentage": "75%", "profiles": [{"profile": "buyers"}, {"profile": "admins"}]})

    first = generate_retrospective_learning_holdout_plan(payload)
    second = generate_retrospective_learning_holdout_plan(payload)

    assert first == second
    assert first["summary"]["holdout_percentage"] == 50
    assert [item["name"] for item in first["holdout_cohorts"]] == ["admins", "buyers"]


def test_retrospective_learning_holdout_plan_uses_sensible_default_percentage() -> None:
    plan = generate_retrospective_learning_holdout_plan({})

    assert plan["summary"]["holdout_percentage"] == 10
    assert plan["holdout_cohorts"][0]["cohort"] == "retrospective feedback holdout"


def _spec(hints: dict) -> dict:
    return {"metadata": {"retrospective_learning_holdout": hints}, "evidence": {"signal_ids": ["rlh-1"]}}
