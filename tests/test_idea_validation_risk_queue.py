from __future__ import annotations

from max.analysis.idea_validation_risk_queue import (
    build_idea_validation_risk_queue,
    render_idea_validation_risk_queue_markdown,
)


def test_idea_validation_risk_queue_scores_core_risk_signals() -> None:
    queue = build_idea_validation_risk_queue(
        [
            {
                "idea_id": "checkout-ai",
                "validation_status": "blocked",
                "blocker_count": 3,
                "evidence_age_days": 120,
                "customer_impact": 0.9,
                "confidence": 0.2,
            },
            {
                "idea_id": "admin-export",
                "validation_status": "validated",
                "blocker_count": 0,
                "evidence_age_days": 7,
                "customer_impact": 0.4,
                "confidence": 0.85,
            },
        ]
    )

    assert queue["schema_version"] == "max.idea_validation_risk_queue.v1"
    assert queue["kind"] == "max.idea_validation_risk_queue"
    assert queue["summary"]["idea_count"] == 2
    high_risk = queue["risk_rows"][0]
    assert high_risk["idea_id"] == "checkout-ai"
    assert high_risk["risk_tier"] == "critical"
    assert high_risk["risk_score"] > queue["risk_rows"][1]["risk_score"]
    assert "3 validation blocker(s)" in high_risk["top_reasons"]
    assert high_risk["next_validation_action"] == "resolve validation blockers before advancing the idea"


def test_idea_validation_risk_queue_sorts_ties_by_idea_id() -> None:
    queue = build_idea_validation_risk_queue(
        [
            {"idea_id": "idea-b", "validation_status": "pending", "blocker_count": 1, "evidence_age_days": 30},
            {"idea_id": "idea-a", "validation_status": "pending", "blocker_count": 1, "evidence_age_days": 30},
        ]
    )

    assert [row["idea_id"] for row in queue["risk_rows"]] == ["idea-a", "idea-b"]


def test_idea_validation_risk_queue_recommends_refresh_for_stale_evidence() -> None:
    queue = build_idea_validation_risk_queue(
        [
            {
                "idea_id": "stale-only",
                "validation_status": "mixed",
                "blocker_count": 0,
                "evidence_age_days": 75,
                "customer_impact": 0.5,
                "confidence": 0.6,
            }
        ]
    )

    row = queue["risk_rows"][0]
    assert row["risk_tier"] == "moderate"
    assert row["next_validation_action"] == "refresh stale evidence with current customer interviews"


def test_idea_validation_risk_queue_markdown_includes_tier_reasons_and_action() -> None:
    queue = build_idea_validation_risk_queue(
        [
            {"idea_id": "z-idea", "validation_status": "validated", "confidence": 0.9},
            {
                "idea_id": "a-idea",
                "validation_status": "unknown",
                "blocker_count": 2,
                "evidence_age_days": 90,
                "confidence": 0.3,
                "customer_impact": 0.8,
            },
        ]
    )

    first = render_idea_validation_risk_queue_markdown(queue)
    second = render_idea_validation_risk_queue_markdown(queue)

    assert first == second
    assert first.startswith("# Idea Validation Risk Queue")
    assert first.index("### a-idea") < first.index("### z-idea")
    assert "- Risk tier:" in first
    assert "- Top reasons:" in first
    assert "- Next validation action:" in first
