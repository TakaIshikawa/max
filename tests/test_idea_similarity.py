"""Tests for BuildableUnit similarity analysis."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from max.analysis.idea_similarity import find_similar_ideas
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def _unit(
    unit_id: str,
    title: str,
    problem: str,
    *,
    insights: list[str] | None = None,
    evidence: list[str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner=problem,
        category=BuildableCategory.APPLICATION,
        problem=problem,
        solution="Build a focused workflow tool",
        value_proposition="Save operators time",
        inspiring_insights=insights or [],
        evidence_signals=evidence or [],
    )


def _store_embedding(store: Store, entity_id: str, embedding: list[float]) -> None:
    store.conn.execute(
        "INSERT INTO embeddings (id, entity_type, embedding) VALUES (?, ?, ?)",
        (entity_id, "buildable_unit", json.dumps(embedding)),
    )
    store.conn.commit()


def test_find_similar_ideas_uses_stored_embeddings_without_recomputing(store: Store) -> None:
    store.insert_buildable_unit(
        _unit("bu-query", "MCP Test Runner", "MCP servers need regression testing")
    )
    store.insert_buildable_unit(
        _unit(
            "bu-match",
            "Protocol Test Harness",
            "MCP servers need protocol checks",
            insights=["ins-shared"],
            evidence=["sig-shared"],
        )
    )
    store.insert_buildable_unit(
        _unit("bu-other", "Invoice Importer", "Finance teams need cleaner CSV imports")
    )
    _store_embedding(store, "bu-query", [1.0, 0.0])
    _store_embedding(store, "bu-match", [0.9, 0.1])
    _store_embedding(store, "bu-other", [0.0, 1.0])

    with patch("max.analysis.idea_similarity.embed_text", side_effect=AssertionError):
        results = find_similar_ideas(
            store,
            idea_id="bu-query",
            threshold=0.5,
            limit=5,
        )

    assert [result.idea_id for result in results] == ["bu-match"]
    assert results[0].title == "Protocol Test Harness"
    assert results[0].similarity_score == pytest.approx(0.9938837)


def test_find_similar_ideas_reports_overlap_for_idea_queries(store: Store) -> None:
    store.insert_buildable_unit(
        _unit(
            "bu-query",
            "MCP Test Runner",
            "MCP servers need regression testing",
            insights=["ins-1", "ins-2"],
            evidence=["sig-1", "sig-2"],
        )
    )
    store.insert_buildable_unit(
        _unit(
            "bu-match",
            "MCP Validator",
            "MCP servers need validation testing",
            insights=["ins-2", "ins-3"],
            evidence=["sig-2", "sig-3"],
        )
    )

    results = find_similar_ideas(store, idea_id="bu-query", threshold=0.1)

    assert results[0].idea_id == "bu-match"
    assert results[0].overlapping_insight_ids == ["ins-2"]
    assert results[0].overlapping_evidence_ids == ["sig-2"]


def test_find_similar_ideas_free_text_uses_deterministic_text_fallback(store: Store) -> None:
    store.insert_buildable_unit(
        _unit("bu-match", "MCP Test Runner", "MCP server testing for CI")
    )
    store.insert_buildable_unit(
        _unit("bu-other", "Payroll Export", "Payroll CSV export cleanup")
    )

    results = find_similar_ideas(
        store,
        query="MCP server testing",
        threshold=0.2,
        limit=2,
    )

    assert [result.idea_id for result in results] == ["bu-match"]


def test_find_similar_ideas_rejects_missing_or_ambiguous_query(store: Store) -> None:
    with pytest.raises(ValueError):
        find_similar_ideas(store)
    with pytest.raises(ValueError):
        find_similar_ideas(store, idea_id="bu-1", query="text")
    with pytest.raises(LookupError):
        find_similar_ideas(store, idea_id="bu-missing")
