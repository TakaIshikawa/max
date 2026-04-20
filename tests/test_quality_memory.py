"""Tests for persisted critique and idea memory."""

from __future__ import annotations

from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def _unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-memory001",
        title="Memory Test Idea",
        one_liner="Tests quality memory",
        category="application",
        problem="No durable critique memory",
        solution="Persist critique rows",
        value_proposition="Better future prompts",
        domain="healthcare",
        rejection_tags=["weak_evidence"],
        quality_score=4.5,
        evidence_rationale="Thin evidence",
    )


def test_insert_and_get_idea_critique(store: Store) -> None:
    store.insert_buildable_unit(_unit())

    critique_id = store.insert_idea_critique(
        "bu-memory001",
        {
            "urgency": 4,
            "buyer_clarity": 3,
            "specificity": 5,
            "evidence_support": 2,
            "feasibility": 7,
            "differentiation": 4,
            "distribution_path": 3,
            "domain_risk": 6,
            "novelty": 5,
            "usefulness": 4,
            "quality_score": 4.3,
            "reasoning": "Buyer and evidence are weak.",
            "rejection_tags": ["weak_evidence", "no_clear_buyer"],
        },
        evidence_pack={"domain_name": "healthcare"},
        pipeline_run_id="run-test",
    )

    rows = store.get_idea_critiques("bu-memory001")

    assert rows[0]["id"] == critique_id
    assert rows[0]["pipeline_run_id"] == "run-test"
    assert rows[0]["dimensions"]["buyer_clarity"] == 3
    assert rows[0]["rejection_tags"] == ["weak_evidence", "no_clear_buyer"]
    assert rows[0]["evidence_pack"]["domain_name"] == "healthcare"


def test_feedback_updates_idea_memory(store: Store) -> None:
    store.insert_buildable_unit(_unit())

    store.insert_feedback("bu-memory001", "rejected", "weak buyer")

    rows = store.get_idea_memory(domain="healthcare", outcome="rejected")
    assert len(rows) == 1
    assert rows[0]["buildable_unit_id"] == "bu-memory001"
    assert rows[0]["rejection_tags"] == ["weak_evidence"]
    assert "weak buyer" in rows[0]["pattern"]


def test_manual_idea_memory_round_trip(store: Store) -> None:
    memory_id = store.insert_idea_memory(
        outcome="quality_rejected",
        pattern="Generic assistant: too broad",
        domain="healthcare",
        rejection_tags=["generic_ai_assistant"],
        score=3.0,
        evidence_rationale="No supporting signals",
    )

    rows = store.get_idea_memory(domain="healthcare")
    assert rows[0]["id"] == memory_id
    assert rows[0]["outcome"] == "quality_rejected"
    assert rows[0]["rejection_tags"] == ["generic_ai_assistant"]
