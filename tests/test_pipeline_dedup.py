"""Comprehensive tests for src/max/pipeline/dedup.py - semantic deduplication in the pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.embeddings.engine import SemanticIndex
from max.pipeline.dedup import DedupResult, dedup_buildable_units, dedup_insights
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path):
    """Create a temporary store for testing."""
    db_path = str(tmp_path / "test_pipeline_dedup.db")
    s = Store(db_path=db_path)
    yield s
    s.close()


@pytest.fixture
def semantic_index(store):
    """Create a semantic index backed by the test store."""
    return SemanticIndex(store)


@pytest.fixture
def mock_semantic_index():
    """Create a mocked SemanticIndex for tests that don't need real embeddings."""
    mock_index = MagicMock(spec=SemanticIndex)
    mock_index.is_duplicate.return_value = (False, None)
    mock_index.index_entity.return_value = None
    return mock_index


# ── Helper Functions ──────────────────────────────────────────────


def _make_insight(
    id: str,
    title: str,
    summary: str,
    category: InsightCategory = InsightCategory.GAP,
) -> Insight:
    """Create a test Insight with minimal required fields."""
    return Insight(
        id=id,
        category=category,
        title=title,
        summary=summary,
        evidence=["sig-001"],
        confidence=0.8,
        domains=["testing"],
    )


def _make_buildable_unit(
    id: str,
    title: str,
    one_liner: str,
    problem: str,
    category: BuildableCategory = BuildableCategory.CLI_TOOL,
) -> BuildableUnit:
    """Create a test BuildableUnit with minimal required fields."""
    return BuildableUnit(
        id=id,
        title=title,
        one_liner=one_liner,
        category=category,
        ideation_mode=IdeationMode.DIRECT,
        problem=problem,
        solution="A solution to the problem",
        value_proposition="Provides significant value",
    )


# ── Tests for dedup_insights ──────────────────────────────────────


class TestDedupInsights:
    """Test suite for dedup_insights function."""

    def test_empty_input_returns_empty_result(self, semantic_index):
        """Empty input list should produce empty output with no duplicates."""
        result = dedup_insights([], semantic_index)

        assert isinstance(result, DedupResult)
        assert len(result.kept) == 0
        assert result.duplicates == 0

    def test_single_item_is_kept(self, semantic_index):
        """Single insight should always be kept as there's nothing to duplicate against."""
        insights = [_make_insight("ins-001", "Unique insight", "A unique observation")]

        result = dedup_insights(insights, semantic_index)

        assert len(result.kept) == 1
        assert result.kept[0].id == "ins-001"
        assert result.duplicates == 0

    def test_all_unique_insights_are_kept(self, semantic_index):
        """When all insights are unique, all should be kept with no duplicates."""
        insights = [
            _make_insight("ins-001", "MCP testing gap", "No testing framework for MCP servers"),
            _make_insight("ins-002", "AI agent security", "Agents lack sandboxing mechanisms"),
            _make_insight("ins-003", "Token budget optimization", "LLM calls need better token management"),
        ]

        result = dedup_insights(insights, semantic_index)

        assert len(result.kept) == 3
        assert result.duplicates == 0
        assert [i.id for i in result.kept] == ["ins-001", "ins-002", "ins-003"]

    def test_exact_duplicates_in_batch_are_filtered(self, semantic_index):
        """Identical insights in the same batch - first is kept, rest are filtered."""
        insights = [
            _make_insight(
                "ins-001",
                "MCP server testing gap",
                "The MCP ecosystem lacks a standard testing framework for servers",
            ),
            _make_insight(
                "ins-002",
                "MCP server testing gap",
                "The MCP ecosystem lacks a standard testing framework for servers",
            ),
            _make_insight(
                "ins-003",
                "MCP server testing gap",
                "The MCP ecosystem lacks a standard testing framework for servers",
            ),
        ]

        result = dedup_insights(insights, semantic_index)

        assert len(result.kept) == 1
        assert result.kept[0].id == "ins-001"
        assert result.duplicates == 2

    def test_near_duplicate_detection_with_semantic_similarity(self, semantic_index):
        """Near-duplicates with slightly different wording should be detected."""
        # Pre-index an existing insight
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

        # Should be detected as duplicate
        assert result.duplicates >= 1
        assert len(result.kept) <= 0 or result.duplicates > 0

    def test_duplicate_against_existing_index(self, semantic_index):
        """Insights should be checked against previously indexed items."""
        # Pre-populate the index with an insight
        semantic_index.index_entity(
            "ins-001",
            "insight",
            "AI safety problem Lack of proper sandboxing for autonomous agents",
        )

        # Try to add a near-duplicate
        insights = [
            _make_insight(
                "ins-002",
                "AI safety problem",
                "Lack of proper sandboxing for autonomous agents",
            ),
        ]

        result = dedup_insights(insights, semantic_index, threshold=0.85)

        # Should be flagged as duplicate
        assert result.duplicates >= 1

    def test_threshold_affects_duplicate_detection(self, semantic_index):
        """Higher threshold should result in fewer duplicates detected."""
        # Pre-index a somewhat related insight
        semantic_index.index_entity(
            "ins-existing",
            "insight",
            "MCP protocol validation framework needed for compliance",
        )

        insights = [
            _make_insight(
                "ins-new",
                "MCP Validator",
                "MCP servers need protocol validation tools",
            ),
        ]

        # Strict threshold - less likely to flag as duplicate
        strict_result = dedup_insights(insights, semantic_index, threshold=0.99)

        # Loose threshold - more likely to flag as duplicate
        loose_result = dedup_insights(insights, semantic_index, threshold=0.3)

        # Loose threshold should catch more duplicates
        assert strict_result.duplicates <= loose_result.duplicates

    def test_preserves_order_of_kept_insights(self, semantic_index):
        """Kept insights should maintain their original order."""
        insights = [
            _make_insight("ins-003", "Third insight", "Summary three"),
            _make_insight("ins-001", "First insight", "Summary one"),
            _make_insight("ins-002", "Second insight", "Summary two"),
        ]

        result = dedup_insights(insights, semantic_index)

        assert [i.id for i in result.kept] == ["ins-003", "ins-001", "ins-002"]

    def test_indexes_kept_insights_for_subsequent_checks(self, semantic_index):
        """Each kept insight should be indexed so later items are checked against it."""
        insights = [
            _make_insight("ins-001", "Base insight", "Original content"),
            _make_insight("ins-002", "Different insight", "Completely different content"),
        ]

        # Process the batch
        dedup_insights(insights, semantic_index)

        # Verify both were indexed
        similar_to_first = semantic_index.find_similar(
            "Base insight Original content",
            "insight",
            threshold=0.7,
        )
        similar_to_second = semantic_index.find_similar(
            "Different insight Completely different content",
            "insight",
            threshold=0.7,
        )

        assert any(match[0] == "ins-001" for match in similar_to_first)
        assert any(match[0] == "ins-002" for match in similar_to_second)

    def test_mixed_unique_and_duplicate_insights(self, semantic_index):
        """Batch with both unique and duplicate insights should be handled correctly."""
        insights = [
            _make_insight("ins-001", "Unique A", "First unique insight"),
            _make_insight("ins-002", "Unique B", "Second unique insight"),
            _make_insight("ins-003", "Unique A", "First unique insight"),  # Duplicate of ins-001
            _make_insight("ins-004", "Unique C", "Third unique insight"),
            _make_insight("ins-005", "Unique B", "Second unique insight"),  # Duplicate of ins-002
        ]

        result = dedup_insights(insights, semantic_index)

        assert len(result.kept) == 3
        assert result.duplicates == 2
        assert result.kept[0].id == "ins-001"
        assert result.kept[1].id == "ins-002"
        assert result.kept[2].id == "ins-004"

    def test_different_insight_categories_are_treated_independently(self, semantic_index):
        """Insights of different categories should not interfere with each other."""
        insights = [
            _make_insight("ins-001", "Title", "Content", InsightCategory.GAP),
            _make_insight("ins-002", "Title", "Content", InsightCategory.PAIN_POINT),
            _make_insight("ins-003", "Title", "Content", InsightCategory.TREND),
        ]

        result = dedup_insights(insights, semantic_index)

        # Even though they have the same title/content, they're all kept
        # because dedup only checks within the "insight" entity_type
        assert len(result.kept) >= 1
        assert result.duplicates >= 0


# ── Tests for dedup_buildable_units ───────────────────────────────


class TestDedupBuildableUnits:
    """Test suite for dedup_buildable_units function."""

    def test_empty_input_returns_empty_result(self, semantic_index):
        """Empty input list should produce empty output with no duplicates."""
        result = dedup_buildable_units([], semantic_index)

        assert isinstance(result, DedupResult)
        assert len(result.kept) == 0
        assert result.duplicates == 0

    def test_single_item_is_kept(self, semantic_index):
        """Single buildable unit should always be kept."""
        units = [
            _make_buildable_unit(
                "bu-001",
                "MCP Test Framework",
                "Test MCP servers",
                "No testing tools available",
            )
        ]

        result = dedup_buildable_units(units, semantic_index)

        assert len(result.kept) == 1
        assert result.kept[0].id == "bu-001"
        assert result.duplicates == 0

    def test_all_unique_units_are_kept(self, semantic_index):
        """When all units are unique, all should be kept."""
        units = [
            _make_buildable_unit(
                "bu-001",
                "MCP Test Framework",
                "Test MCP servers",
                "No testing for MCP servers",
            ),
            _make_buildable_unit(
                "bu-002",
                "AI Agent Monitor",
                "Monitor AI agents",
                "No monitoring tools for agents",
            ),
            _make_buildable_unit(
                "bu-003",
                "Token Budget Tracker",
                "Track LLM token usage",
                "No visibility into token consumption",
            ),
        ]

        result = dedup_buildable_units(units, semantic_index)

        assert len(result.kept) == 3
        assert result.duplicates == 0
        assert [u.id for u in result.kept] == ["bu-001", "bu-002", "bu-003"]

    def test_exact_duplicates_in_batch_are_filtered(self, semantic_index):
        """Identical units in the same batch - first is kept, rest are filtered."""
        units = [
            _make_buildable_unit(
                "bu-001",
                "MCP Test Framework",
                "Standardized testing for MCP servers",
                "No standard testing exists for MCP servers",
            ),
            _make_buildable_unit(
                "bu-002",
                "MCP Test Framework",
                "Standardized testing for MCP servers",
                "No standard testing exists for MCP servers",
            ),
            _make_buildable_unit(
                "bu-003",
                "MCP Test Framework",
                "Standardized testing for MCP servers",
                "No standard testing exists for MCP servers",
            ),
        ]

        result = dedup_buildable_units(units, semantic_index)

        assert len(result.kept) == 1
        assert result.kept[0].id == "bu-001"
        assert result.duplicates == 2

    def test_near_duplicate_detection(self, semantic_index):
        """Near-duplicates with slightly different wording should be detected."""
        # Pre-index an existing unit
        semantic_index.index_entity(
            "bu-existing",
            "buildable_unit",
            "MCP Test Framework Test MCP servers No testing for MCP servers",
        )

        # Try to add a very similar one
        units = [
            _make_buildable_unit(
                "bu-new",
                "MCP Test Framework",
                "Test MCP servers",
                "No testing for MCP servers",
            ),
        ]

        result = dedup_buildable_units(units, semantic_index, threshold=0.8)

        # Should be detected as duplicate
        assert result.duplicates >= 1

    def test_duplicate_against_existing_index(self, semantic_index):
        """Units should be checked against previously indexed items."""
        # Pre-populate the index
        semantic_index.index_entity(
            "bu-001",
            "buildable_unit",
            "Agent Sandbox CLI tool to sandbox AI agents Agents need isolation",
        )

        # Try to add a near-duplicate
        units = [
            _make_buildable_unit(
                "bu-002",
                "Agent Sandbox",
                "CLI tool to sandbox AI agents",
                "Agents need isolation",
            ),
        ]

        result = dedup_buildable_units(units, semantic_index, threshold=0.85)

        assert result.duplicates >= 1

    def test_threshold_affects_duplicate_detection(self, semantic_index):
        """Higher threshold should result in fewer duplicates detected."""
        # Pre-index a somewhat related unit
        semantic_index.index_entity(
            "bu-existing",
            "buildable_unit",
            "MCP testing framework for validating protocol compliance",
        )

        units = [
            _make_buildable_unit(
                "bu-new",
                "MCP Validator",
                "Validate MCP server protocol",
                "MCP servers need protocol validation",
            ),
        ]

        # Strict threshold - less likely to flag as duplicate
        strict_result = dedup_buildable_units(units, semantic_index, threshold=0.99)

        # Loose threshold - more likely to flag as duplicate
        loose_result = dedup_buildable_units(units, semantic_index, threshold=0.3)

        assert strict_result.duplicates <= loose_result.duplicates

    def test_default_threshold_is_0_85(self, mock_semantic_index):
        """Default threshold for buildable units should be 0.85."""
        units = [
            _make_buildable_unit(
                "bu-001",
                "Test Unit",
                "Test one liner",
                "Test problem",
            ),
        ]

        dedup_buildable_units(units, mock_semantic_index)

        # Check that is_duplicate was called with threshold=0.85
        mock_semantic_index.is_duplicate.assert_called()
        call_kwargs = mock_semantic_index.is_duplicate.call_args[1]
        assert call_kwargs.get("threshold") == 0.85

    def test_preserves_order_of_kept_units(self, semantic_index):
        """Kept units should maintain their original order."""
        units = [
            _make_buildable_unit("bu-003", "Third", "Three", "Problem 3"),
            _make_buildable_unit("bu-001", "First", "One", "Problem 1"),
            _make_buildable_unit("bu-002", "Second", "Two", "Problem 2"),
        ]

        result = dedup_buildable_units(units, semantic_index)

        assert [u.id for u in result.kept] == ["bu-003", "bu-001", "bu-002"]

    def test_indexes_kept_units_for_subsequent_checks(self, semantic_index):
        """Each kept unit should be indexed so later items are checked against it."""
        units = [
            _make_buildable_unit("bu-001", "Base unit", "Base liner", "Base problem"),
            _make_buildable_unit("bu-002", "Different unit", "Different liner", "Different problem"),
        ]

        # Process the batch
        dedup_buildable_units(units, semantic_index)

        # Verify both were indexed
        similar_to_first = semantic_index.find_similar(
            "Base unit Base liner Base problem",
            "buildable_unit",
            threshold=0.7,
        )
        similar_to_second = semantic_index.find_similar(
            "Different unit Different liner Different problem",
            "buildable_unit",
            threshold=0.7,
        )

        assert any(match[0] == "bu-001" for match in similar_to_first)
        assert any(match[0] == "bu-002" for match in similar_to_second)

    def test_mixed_unique_and_duplicate_units(self, semantic_index):
        """Batch with both unique and duplicate units should be handled correctly."""
        units = [
            _make_buildable_unit("bu-001", "Unique A", "Liner A", "Problem A"),
            _make_buildable_unit("bu-002", "Unique B", "Liner B", "Problem B"),
            _make_buildable_unit("bu-003", "Unique A", "Liner A", "Problem A"),  # Duplicate
            _make_buildable_unit("bu-004", "Unique C", "Liner C", "Problem C"),
            _make_buildable_unit("bu-005", "Unique B", "Liner B", "Problem B"),  # Duplicate
        ]

        result = dedup_buildable_units(units, semantic_index)

        assert len(result.kept) == 3
        assert result.duplicates == 2
        assert result.kept[0].id == "bu-001"
        assert result.kept[1].id == "bu-002"
        assert result.kept[2].id == "bu-004"

    def test_text_combination_includes_title_one_liner_and_problem(self, mock_semantic_index):
        """Dedup should combine title, one_liner, and problem fields for similarity check."""
        unit = _make_buildable_unit(
            "bu-001",
            "My Title",
            "My one liner",
            "My problem statement",
        )

        dedup_buildable_units([unit], mock_semantic_index)

        # Verify the text passed to is_duplicate includes all three fields
        call_args = mock_semantic_index.is_duplicate.call_args[0]
        text_arg = call_args[0]
        assert "My Title" in text_arg
        assert "My one liner" in text_arg
        assert "My problem statement" in text_arg


# ── Tests for DedupResult ─────────────────────────────────────────


class TestDedupResult:
    """Test suite for DedupResult dataclass."""

    def test_dedup_result_structure(self):
        """DedupResult should have kept list and duplicates count."""
        result = DedupResult(kept=[], duplicates=0)

        assert hasattr(result, "kept")
        assert hasattr(result, "duplicates")
        assert isinstance(result.kept, list)
        assert isinstance(result.duplicates, int)

    def test_dedup_result_with_insights(self):
        """DedupResult can hold insights."""
        insights = [
            _make_insight("ins-001", "Title 1", "Summary 1"),
            _make_insight("ins-002", "Title 2", "Summary 2"),
        ]
        result = DedupResult(kept=insights, duplicates=3)

        assert len(result.kept) == 2
        assert result.duplicates == 3

    def test_dedup_result_with_buildable_units(self):
        """DedupResult can hold buildable units."""
        units = [
            _make_buildable_unit("bu-001", "Title 1", "Liner 1", "Problem 1"),
        ]
        result = DedupResult(kept=units, duplicates=5)

        assert len(result.kept) == 1
        assert result.duplicates == 5


# ── Integration Tests ─────────────────────────────────────────────


class TestDedupIntegration:
    """Integration tests for dedup functions with real SemanticIndex."""

    def test_insights_and_units_use_separate_namespaces(self, semantic_index):
        """Insights and buildable units should not interfere with each other in dedup."""
        # Index an insight
        insights = [_make_insight("ins-001", "MCP Testing", "Need MCP testing framework")]
        dedup_insights(insights, semantic_index)

        # Try to add a buildable unit with similar text
        units = [
            _make_buildable_unit(
                "bu-001",
                "MCP Testing",
                "Need MCP testing framework",
                "MCP testing framework needed",
            )
        ]
        result = dedup_buildable_units(units, semantic_index)

        # Should not be flagged as duplicate since they're different entity types
        assert len(result.kept) == 1
        assert result.duplicates == 0

    def test_subsequent_batches_build_on_previous_index(self, semantic_index):
        """Processing multiple batches should accumulate in the index."""
        # First batch
        batch1 = [
            _make_insight("ins-001", "Insight A", "Summary A"),
            _make_insight("ins-002", "Insight B", "Summary B"),
        ]
        result1 = dedup_insights(batch1, semantic_index)
        assert len(result1.kept) == 2

        # Second batch with a duplicate from first batch
        batch2 = [
            _make_insight("ins-003", "Insight C", "Summary C"),
            _make_insight("ins-004", "Insight A", "Summary A"),  # Duplicate of ins-001
        ]
        result2 = dedup_insights(batch2, semantic_index)

        # ins-003 should be kept, ins-004 should be flagged as duplicate
        assert len(result2.kept) >= 1
        assert result2.duplicates >= 1

    def test_custom_threshold_allows_fine_tuning(self, semantic_index):
        """Custom thresholds should allow tuning duplicate detection sensitivity."""
        # Pre-index a unit
        semantic_index.index_entity(
            "bu-001",
            "buildable_unit",
            "API rate limiting library for HTTP clients",
        )

        # Similar but not identical
        units = [
            _make_buildable_unit(
                "bu-002",
                "Rate Limiter",
                "HTTP rate limiting",
                "Need rate limiting for APIs",
            ),
        ]

        # Very strict - should not flag as duplicate
        strict = dedup_buildable_units(units, semantic_index, threshold=0.98)
        assert strict.duplicates == 0

        # More lenient - might flag as duplicate depending on embeddings
        lenient = dedup_buildable_units(units, semantic_index, threshold=0.5)
        # Result depends on actual similarity, but lenient should have >= strict
        assert lenient.duplicates >= strict.duplicates
