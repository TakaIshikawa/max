from __future__ import annotations

from max.analysis.feedback_outcome_learning_digest import (
    build_feedback_outcome_learning_digest,
    render_feedback_outcome_learning_digest_markdown,
)


def test_feedback_outcome_learning_digest_groups_by_required_dimensions() -> None:
    digest = build_feedback_outcome_learning_digest(
        [
            {"profile": "admin", "category": "security", "source": "calls", "recommendation_status": "recommended", "outcome": "approved"},
            {"profile": "admin", "category": "security", "source": "calls", "recommendation_status": "recommended", "outcome": "shipped"},
            {"profile": "admin", "category": "security", "source": "survey", "recommendation_status": "recommended", "outcome": "rejected", "rejection_reason": "low trust"},
        ]
    )

    assert digest["schema_version"] == "max.feedback_outcome_learning_digest.v1"
    assert digest["kind"] == "max.feedback_outcome_learning_digest"
    assert digest["summary"]["outcome_count"] == 3
    assert digest["summary"]["group_count"] == 2
    rows = {(row["profile"], row["category"], row["source"], row["recommendation_status"]): row for row in digest["learning_rows"]}
    assert rows[("admin", "security", "calls", "recommended")]["outcome_count"] == 2
    assert rows[("admin", "security", "survey", "recommended")]["top_rejection_reason"] == "low trust"


def test_feedback_outcome_learning_digest_calculates_rates_and_learning() -> None:
    digest = build_feedback_outcome_learning_digest(
        [
            {"profile": "buyer", "category": "roi", "source": "panel", "recommendation_status": "recommended", "outcome": "approved", "shipped": True},
            {"profile": "buyer", "category": "roi", "source": "panel", "recommendation_status": "recommended", "outcome": "approved"},
            {"profile": "buyer", "category": "roi", "source": "panel", "recommendation_status": "recommended", "outcome": "approved", "shipped": True},
            {"profile": "buyer", "category": "roi", "source": "panel", "recommendation_status": "recommended", "outcome": "rejected", "rejection_reason": "duplicate"},
        ]
    )

    row = digest["learning_rows"][0]
    assert row["approval_rate"] == 0.75
    assert row["shipped_rate"] == 0.5
    assert row["recommended_learning"] == "increase scoring weight and preserve source strategy"


def test_feedback_outcome_learning_digest_detects_negative_reason_concentration() -> None:
    digest = build_feedback_outcome_learning_digest(
        [
            {"profile": "seller", "category": "workflow", "source": "tickets", "recommendation_status": "recommended", "outcome": "rejected", "rejection_reason": "not urgent"},
            {"profile": "seller", "category": "workflow", "source": "tickets", "recommendation_status": "recommended", "outcome": "rejected", "rejection_reason": "not urgent"},
            {"profile": "seller", "category": "workflow", "source": "tickets", "recommendation_status": "recommended", "outcome": "approved"},
        ]
    )

    row = digest["learning_rows"][0]
    assert row["approval_rate"] == 0.3333
    assert row["rejection_reason_concentration"] == 1.0
    assert row["recommended_learning"] == "reduce scoring weight; investigate not urgent"


def test_feedback_outcome_learning_digest_markdown_highlights_signals() -> None:
    digest = build_feedback_outcome_learning_digest(
        [
            {"profile": "a", "category": "cat", "source": "good", "recommendation_status": "recommended", "outcome": "approved", "shipped": True},
            {"profile": "a", "category": "cat", "source": "bad", "recommendation_status": "recommended", "outcome": "rejected", "rejection_reason": "wrong segment"},
            {"profile": "a", "category": "cat", "source": "bad", "recommendation_status": "recommended", "outcome": "rejected", "rejection_reason": "wrong segment"},
        ]
    )

    first = render_feedback_outcome_learning_digest_markdown(digest)
    second = render_feedback_outcome_learning_digest_markdown(digest)

    assert first == second
    assert first.startswith("# Feedback Outcome Learning Digest")
    assert "## Strongest Positive Learning Signals" in first
    assert "## Strongest Negative Learning Signals" in first
    assert "- Recommended learning:" in first
