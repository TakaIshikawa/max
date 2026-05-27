from __future__ import annotations

import json

from max.spec.model_eval_judge_calibration_plan import generate_model_eval_judge_calibration_plan


def test_model_eval_judge_calibration_plan_flags_missing_threshold_and_reviewers() -> None:
    plan = generate_model_eval_judge_calibration_plan(_spec("model_eval_judge_calibration", {}))

    assert [item["name"] for item in plan["blockers"]] == [
        "missing disagreement threshold",
        "missing calibration reviewers",
    ]
    assert plan["disagreement_thresholds"][0]["name"] == "human-judge disagreement <= 5 percent and critical disagreement = 0"


def test_model_eval_judge_calibration_plan_warns_on_gold_example_coverage() -> None:
    plan = generate_model_eval_judge_calibration_plan(
        _spec(
            "model_eval_judge_calibration",
            {
                "max_disagreement_rate": "5%",
                "reviewers": ["qa lead"],
                "gold_examples": ["pass", "fail"],
                "minimum_gold_examples": 3,
            },
        )
    )

    assert plan["blockers"] == []
    assert plan["warnings"][0]["name"] == "insufficient gold example coverage"
    assert plan["summary"]["gold_example_count"] == 2


def test_model_eval_judge_calibration_plan_preserves_metadata_and_is_deterministic() -> None:
    payload = _spec(
        "model_eval_judge_calibration",
        {"max_disagreement_rate": "3%", "reviewers": ["qa lead"], "gold_examples": ["a", "b", "c"]},
    )
    plan = generate_model_eval_judge_calibration_plan(payload)

    assert plan == generate_model_eval_judge_calibration_plan(payload)
    assert json.loads(json.dumps(plan)) == plan
    assert plan["source"]["idea_id"] == "idea-1"
    assert plan["reviewer_assignments"][0]["name"] == "qa lead"


def _spec(key: str, hints: dict) -> dict:
    return {"source": {"idea_id": "idea-1"}, "metadata": {key: hints}, "evidence": {"signal_ids": ["sig-1"]}}
