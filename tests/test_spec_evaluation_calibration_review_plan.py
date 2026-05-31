from __future__ import annotations

from max.spec import generate_evaluation_calibration_review_plan


def test_evaluation_calibration_review_plan_thresholds_and_ordering() -> None:
    plan = generate_evaluation_calibration_review_plan(
        {
            "metadata": {
                "evaluation_calibration_review": {
                    "dimensions": [
                        {"name": "correctness", "approvals": 10, "rejections": 2, "golden_examples": 5, "disagreement_rate": 0.1},
                        {"name": "evidence", "approvals": 2, "rejections": 7, "golden_examples": 4, "disagreement_rate": 0.1},
                        {"name": "risk", "approvals": 3, "rejections": 1, "golden_examples": 0},
                    ],
                    "examples": [{"id": "a1", "outcome": "approve"}, {"id": "r1", "outcome": "reject"}, {"id": "g1", "outcome": "golden"}],
                }
            }
        }
    )

    assert list(plan)[:5] == ["schema_version", "kind", "source", "summary", "sampling_strategy"]
    assert [row["recommendation"] for row in plan["dimension_reviews"]] == ["recalibrate", "tighten", "hold"]
    assert plan["dimension_reviews"][0]["name"] == "risk"
    assert plan["sampling_strategy"][0]["available_examples"] == 1
    assert plan["adoption_metrics"][0]["name"] == "reviewer_agreement_rate"


def test_evaluation_calibration_review_plan_stable_with_dimensions_without_examples() -> None:
    first = generate_evaluation_calibration_review_plan({"dimensions": ["helpfulness"]})
    second = generate_evaluation_calibration_review_plan({"dimensions": ["helpfulness"]})

    assert first == second
    assert first["dimension_reviews"][0]["golden_examples"] == 0
    assert first["dimension_reviews"][0]["recommendation"] == "recalibrate"
