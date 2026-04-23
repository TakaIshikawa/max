"""Tests for deterministic idea revision briefs."""

from __future__ import annotations

import copy

import pytest

from max.analysis.revision_brief import REVISION_BRIEF_SCHEMA_VERSION, build_revision_brief


def test_revision_brief_combines_feedback_critique_evaluation_and_prior_art(
    store,
    sample_unit,
    sample_evaluation,
) -> None:
    sample_unit.buyer = ""
    sample_unit.status = "rejected"
    sample_unit.prior_art_status = "strong_match"
    sample_unit.rejection_tags = ["no_clear_buyer"]
    store.insert_buildable_unit(sample_unit)
    sample_evaluation.weaknesses = ["Buyer is unclear", "Niche audience"]
    store.insert_evaluation(sample_evaluation)
    store.insert_feedback(sample_unit.id, "rejected", "Buyer and differentiation are weak")
    store.insert_idea_critique(
        sample_unit.id,
        {
            "buyer_clarity": 3.0,
            "differentiation": 4.0,
            "evidence_support": 5.0,
            "reasoning": "Needs a sharper wedge.",
            "rejection_tags": ["weak_evidence"],
        },
        evidence_pack={},
    )
    store.insert_prior_art_match(
        sample_unit.id,
        {
            "source": "github",
            "title": "Existing MCP Tester",
            "url": "https://example.com/mcp-tester",
            "description": "Similar test framework",
            "relevance_score": 0.9,
            "match_signals": {"stars": 99},
            "search_query": "mcp test",
        },
    )

    first = build_revision_brief(store, sample_unit.id)
    second = build_revision_brief(store, sample_unit.id)

    assert first == second
    assert first["schema_version"] == REVISION_BRIEF_SCHEMA_VERSION
    assert first["idea_id"] == sample_unit.id
    assert first["latest_feedback"]["outcome"] == "rejected"
    assert first["current_state"]["prior_art_status"] == "strong_match"
    assert first["current_state"]["evaluation"]["overall_score"] == 78.0
    assert any(defect["source"] == "feedback" for defect in first["key_defects"])
    assert any(defect["source"] == "prior_art" for defect in first["key_defects"])
    fields = [item["field"] for item in first["fields_to_update"]]
    assert "buyer" in fields
    assert "agent_prompt" in first


def test_revision_brief_does_not_mutate_idea(store, sample_unit) -> None:
    original = copy.deepcopy(sample_unit.model_dump())
    store.insert_buildable_unit(sample_unit)

    build_revision_brief(store, sample_unit.id)

    refreshed = store.get_buildable_unit(sample_unit.id)
    assert refreshed is not None
    assert refreshed.model_dump() == original


def test_revision_brief_missing_idea_raises(store) -> None:
    with pytest.raises(ValueError, match="Idea not found"):
        build_revision_brief(store, "bu-missing")
