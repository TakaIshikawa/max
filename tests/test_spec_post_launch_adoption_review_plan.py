from __future__ import annotations

from max.spec.post_launch_adoption_review_plan import KIND, SCHEMA_VERSION, generate_post_launch_adoption_review_plan


def test_post_launch_adoption_review_marks_below_target_metrics_at_risk() -> None:
    plan = generate_post_launch_adoption_review_plan(
        {
            "evidence": {"insight_ids": ["ins-1"]},
            "metadata": {
                "post_launch_adoption_review": {
                    "adoption_metrics": [{"name": "activation", "actual": 42, "target": 60}],
                    "cohort_segments": ["SMB", "Enterprise"],
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["adoption_status"] == "at_risk"
    assert plan["adoption_metrics"][0]["status"] == "below_target"
    assert plan["intervention_actions"]
    assert plan["adoption_metrics"][0]["evidence_reference_ids"] == ["EV1"]


def test_post_launch_adoption_review_normalizes_string_metric() -> None:
    plan = generate_post_launch_adoption_review_plan({"metadata": {"post_launch_adoption_review": {"metrics": ["weekly active users"]}}})

    assert plan["adoption_metrics"][0]["id"] == "PLM1"
    assert plan["adoption_metrics"][0]["name"] == "weekly active users"
