"""Tests for semantic deduplication in the pipeline."""

from __future__ import annotations

import pytest

from max.embeddings.engine import SemanticIndex
from max.pipeline.dedup import dedup_buildable_units, dedup_insights
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_dedup.db")
    s = Store(db_path=db_path)
    yield s
    s.close()


@pytest.fixture
def semantic_index(store):
    return SemanticIndex(store)


def _make_insight(id: str, title: str, summary: str) -> Insight:
    return Insight(
        id=id,
        category=InsightCategory.GAP,
        title=title,
        summary=summary,
        evidence=["sig-001"],
        confidence=0.8,
        domains=["testing"],
    )


def _make_unit(id: str, title: str, one_liner: str, problem: str) -> BuildableUnit:
    return BuildableUnit(
        id=id,
        title=title,
        one_liner=one_liner,
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem=problem,
        solution="A solution",
        value_proposition="Some value",
    )


# ── Insight dedup ─────────────────────────────────────────────────


def test_dedup_keeps_novel_insights(semantic_index):
    """Unrelated insights should all be kept."""
    insights = [
        _make_insight("ins-001", "MCP testing gap", "No testing framework for MCP servers"),
        _make_insight("ins-002", "AI agent security", "Agents lack sandboxing mechanisms"),
    ]

    result = dedup_insights(insights, semantic_index)
    assert len(result.kept) == 2
    assert result.duplicates == 0


def test_dedup_filters_duplicate_insight(semantic_index):
    """A near-identical insight should be filtered out."""
    # Index an existing insight first
    semantic_index.index_entity(
        "ins-existing",
        "insight",
        "MCP testing gap No testing framework for MCP servers exists",
    )

    # Try to add a very similar one
    insights = [
        _make_insight(
            "ins-new",
            "MCP testing gap",
            "No testing framework for MCP servers exists today",
        ),
    ]

    result = dedup_insights(insights, semantic_index, threshold=0.8)
    assert result.duplicates >= 1
    assert len(result.kept) <= 0 or result.duplicates > 0


def test_dedup_within_insight_batch(semantic_index):
    """Two similar insights in the same batch — second should be filtered."""
    insights = [
        _make_insight(
            "ins-001",
            "MCP server testing is missing",
            "The MCP ecosystem has no standard testing framework for servers",
        ),
        _make_insight(
            "ins-002",
            "MCP server testing is missing",
            "The MCP ecosystem has no standard testing framework for servers",
        ),
    ]

    result = dedup_insights(insights, semantic_index)
    assert len(result.kept) == 1
    assert result.duplicates == 1
    assert result.kept[0].id == "ins-001"


def test_dedup_empty_index_keeps_all(semantic_index):
    """With no existing embeddings, all insights are kept."""
    insights = [
        _make_insight("ins-001", "Insight A", "Summary A"),
        _make_insight("ins-002", "Insight B", "Summary B"),
    ]

    result = dedup_insights(insights, semantic_index)
    assert len(result.kept) == 2
    assert result.duplicates == 0


def test_dedup_empty_input(semantic_index):
    """Empty input produces empty output."""
    result = dedup_insights([], semantic_index)
    assert len(result.kept) == 0
    assert result.duplicates == 0


# ── BuildableUnit dedup ───────────────────────────────────────────


def test_dedup_keeps_novel_units(semantic_index):
    """Unrelated units should all be kept."""
    units = [
        _make_unit("bu-001", "MCP Test Framework", "Test MCP servers", "No testing"),
        _make_unit("bu-002", "AI Agent Monitor", "Monitor AI agents", "No monitoring"),
    ]

    result = dedup_buildable_units(units, semantic_index)
    assert len(result.kept) == 2
    assert result.duplicates == 0


def test_dedup_filters_duplicate_unit(semantic_index):
    """A near-identical unit should be filtered out."""
    semantic_index.index_entity(
        "bu-existing",
        "buildable_unit",
        "MCP Test Framework Test MCP servers No testing for MCP servers",
    )

    units = [
        _make_unit(
            "bu-new",
            "MCP Test Framework",
            "Test MCP servers",
            "No testing for MCP servers",
        ),
    ]

    result = dedup_buildable_units(units, semantic_index, threshold=0.8)
    assert result.duplicates >= 1


def test_dedup_within_unit_batch(semantic_index):
    """Two identical units in same batch — second filtered."""
    units = [
        _make_unit(
            "bu-001",
            "MCP Test Framework",
            "Standardized testing for MCP servers",
            "No standard testing exists for MCP servers",
        ),
        _make_unit(
            "bu-002",
            "MCP Test Framework",
            "Standardized testing for MCP servers",
            "No standard testing exists for MCP servers",
        ),
    ]

    result = dedup_buildable_units(units, semantic_index)
    assert len(result.kept) == 1
    assert result.duplicates == 1
    assert result.kept[0].id == "bu-001"


def test_dedup_threshold_affects_filtering(semantic_index):
    """Higher threshold means fewer duplicates detected."""
    semantic_index.index_entity(
        "bu-existing",
        "buildable_unit",
        "MCP testing framework for validating protocol compliance",
    )

    units = [
        _make_unit(
            "bu-new",
            "MCP Validator",
            "Validate MCP server protocol",
            "MCP servers need protocol validation",
        ),
    ]

    # Strict threshold — less likely to flag as duplicate
    strict = dedup_buildable_units(units, semantic_index, threshold=0.99)
    # Loose threshold — more likely to flag
    loose = dedup_buildable_units(units, semantic_index, threshold=0.3)

    assert strict.duplicates <= loose.duplicates
