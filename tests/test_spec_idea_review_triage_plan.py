from __future__ import annotations

from max.spec import generate_idea_review_triage_plan


def test_idea_review_triage_plan_prioritizes_stale_and_high_score_pending_ideas() -> None:
    plan = generate_idea_review_triage_plan(
        {
            "metadata": {
                "idea_review_triage": {
                    "ideas": [
                        {"id": "fresh-high", "status": "pending", "score": 0.95, "age_hours": 10},
                        {"id": "stale-low", "status": "pending", "score": 0.2, "age_hours": 100},
                        {"id": "stale-high", "status": "pending", "score": 0.9, "age_hours": 80},
                    ]
                }
            }
        }
    )

    assert [item["id"] for item in plan["triage_queue"]] == ["stale-high", "stale-low", "fresh-high"]
    assert plan["summary"]["stale_idea_count"] == 2
    assert plan["triage_queue"][0]["reviewer_hint"] == "lead_reviewer"


def test_idea_review_triage_plan_excludes_approved_and_rejected_ideas() -> None:
    plan = generate_idea_review_triage_plan(
        {"ideas": [{"id": "approved", "status": "approved", "score": 1.0}, {"id": "rejected", "status": "rejected", "score": 1.0}, {"id": "pending", "status": "pending", "score": 0.4}]}
    )

    assert [item["id"] for item in plan["triage_queue"]] == ["pending"]
    assert plan["reviewer_queues"][0]["idea_ids"] == ["pending"]


def test_idea_review_triage_plan_includes_escalation_and_completion_checks() -> None:
    plan = generate_idea_review_triage_plan({})

    assert plan["reviewer_queues"][0]["reviewer"] == "no_pending_reviewer"
    assert plan["escalation_criteria"][0]["name"] == "stale_high_score"
    assert plan["completion_checks"][0]["name"] == "pending_queue_empty"
