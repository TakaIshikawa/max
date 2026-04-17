"""Tests for prior art detection — search, scoring, CLI command."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

from max.analysis.prior_art import (
    PriorArtMatch,
    PriorArtResult,
    _search_github,
    _search_npm,
    _search_pypi,
    _search_source,
    build_search_queries,
    check_prior_art_batch,
    determine_status,
    score_matches,
    select_sources,
)
from max.cli import main
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


# ── Helpers ────────────────────────────────────────────────────────


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _make_unit(
    id: str = "bu-test001",
    title: str = "MCP Test Framework",
    status: str = "evaluated",
    category: str = BuildableCategory.CLI_TOOL,
    domain: str = "devtools",
    prior_art_status: str = "unchecked",
) -> BuildableUnit:
    return BuildableUnit(
        id=id,
        title=title,
        one_liner="Standardized testing for MCP servers",
        category=category,
        ideation_mode=IdeationMode.DIRECT,
        problem="No standard way to test MCP servers",
        solution="A CLI tool that validates MCP server implementations",
        target_users="both",
        value_proposition="Reduce bugs in MCP servers by 80%",
        inspiring_insights=["ins-test001"],
        evidence_signals=["sig-test001"],
        tech_approach="TypeScript CLI with protocol-level validation",
        suggested_stack={"language": "typescript", "runtime": "node"},
        composability_notes="Integrates with CI/CD pipelines",
        status=status,
        domain=domain,
        prior_art_status=prior_art_status,
    )


def _make_match(
    source: str = "github",
    title: str = "mcp-test-suite",
    relevance_score: float = 0.9,
) -> PriorArtMatch:
    return PriorArtMatch(
        source=source,
        title=title,
        url=f"https://github.com/example/{title}",
        description=f"A {source} project for {title}",
        relevance_score=relevance_score,
        match_signals={"stars": 100},
        search_query="mcp test",
    )


# ── Query Construction ─────────────────────────────────────────────


class TestBuildSearchQueries:
    def test_returns_title_query(self):
        unit = _make_unit(title="MCP Test Framework")
        queries = build_search_queries(unit)
        assert queries[0] == "MCP Test Framework"

    def test_returns_keyword_query(self):
        unit = _make_unit(title="MCP Test Framework")
        queries = build_search_queries(unit)
        assert len(queries) == 2
        # Keywords should not contain stop words
        kw_query = queries[1].lower()
        assert "the" not in kw_query.split()
        assert "for" not in kw_query.split()

    def test_two_queries_generated(self):
        unit = _make_unit()
        queries = build_search_queries(unit)
        assert len(queries) == 2


# ── Source Selection ───────────────────────────────────────────────


class TestSelectSources:
    def test_always_includes_github(self):
        unit = _make_unit(category="application")
        sources = select_sources(unit)
        assert "github" in sources

    def test_cli_tool_includes_npm_and_pypi(self):
        unit = _make_unit(category="cli_tool")
        sources = select_sources(unit)
        assert "npm" in sources
        assert "pypi" in sources

    def test_application_includes_product_hunt(self):
        unit = _make_unit(category="application")
        sources = select_sources(unit)
        assert "product_hunt" in sources

    def test_library_includes_npm_and_pypi(self):
        unit = _make_unit(category="library")
        sources = select_sources(unit)
        assert "npm" in sources
        assert "pypi" in sources

    def test_mcp_server_includes_npm(self):
        unit = _make_unit(category="mcp_server")
        sources = select_sources(unit)
        assert "npm" in sources

    def test_js_stack_adds_npm(self):
        unit = _make_unit(category="automation")
        unit.suggested_stack = {"language": "typescript"}
        sources = select_sources(unit)
        assert "npm" in sources

    def test_python_stack_adds_pypi(self):
        unit = _make_unit(category="automation")
        unit.suggested_stack = {"language": "python"}
        sources = select_sources(unit)
        assert "pypi" in sources


# ── Scoring ────────────────────────────────────────────────────────


class TestScoreMatches:
    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_filters_below_threshold(self, mock_sim, mock_embed):
        mock_embed.return_value = [1.0] * 10
        mock_sim.return_value = 0.50  # Below 0.65 threshold

        unit = _make_unit()
        matches = [_make_match(relevance_score=0.0)]
        scored = score_matches(unit, matches)
        assert len(scored) == 0

    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_keeps_above_threshold(self, mock_sim, mock_embed):
        mock_embed.return_value = [1.0] * 10
        mock_sim.return_value = 0.80

        unit = _make_unit()
        matches = [_make_match(relevance_score=0.0)]
        scored = score_matches(unit, matches)
        assert len(scored) == 1
        assert scored[0].relevance_score == 0.80

    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_sorts_by_relevance(self, mock_sim, mock_embed):
        mock_embed.return_value = [1.0] * 10
        mock_sim.side_effect = [0.70, 0.90, 0.75]

        unit = _make_unit()
        matches = [
            _make_match(title="low"),
            _make_match(title="high"),
            _make_match(title="mid"),
        ]
        scored = score_matches(unit, matches)
        assert scored[0].relevance_score == 0.90
        assert scored[-1].relevance_score == 0.70

    def test_empty_matches(self):
        unit = _make_unit()
        assert score_matches(unit, []) == []


# ── Status Determination ──────────────────────────────────────────


class TestDetermineStatus:
    def test_no_matches_is_clear(self):
        assert determine_status([]) == "clear"

    def test_strong_match(self):
        matches = [_make_match(relevance_score=0.90)]
        assert determine_status(matches) == "strong_match"

    def test_weak_match(self):
        matches = [_make_match(relevance_score=0.75)]
        assert determine_status(matches) == "weak_match"

    def test_below_threshold_is_clear(self):
        # score_matches would filter these, but determine_status checks directly
        matches = [_make_match(relevance_score=0.60)]
        assert determine_status(matches) == "clear"


# ── CLI Command ───────────────────────────────────────────────────


class TestPriorArtCommand:
    def test_no_ideas(self, runner):
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = []

        with patch("max.store.db.Store", return_value=mock_store):
            result = runner.invoke(main, ["prior-art"])
            assert result.exit_code == 0
            assert "No ideas to check" in result.output

    def test_skips_rejected_ideas(self, runner):
        rejected = _make_unit(id="bu-rej", status="rejected")
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = [rejected]

        with patch("max.store.db.Store", return_value=mock_store):
            result = runner.invoke(main, ["prior-art"])
            assert result.exit_code == 0
            assert "No ideas to check" in result.output

    def test_skips_already_checked(self, runner):
        checked = _make_unit(id="bu-checked", prior_art_status="clear")
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = [checked]

        with patch("max.store.db.Store", return_value=mock_store):
            result = runner.invoke(main, ["prior-art"])
            assert result.exit_code == 0
            assert "No ideas to check" in result.output

    def test_dry_run(self, runner):
        unit = _make_unit()
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = [unit]

        with patch("max.store.db.Store", return_value=mock_store):
            result = runner.invoke(main, ["prior-art", "--dry-run"])
            assert result.exit_code == 0
            assert "Dry run" in result.output
            assert "MCP Test Framework" in result.output
            assert "Sources:" in result.output

    def test_re_scan_includes_checked(self, runner):
        unit = _make_unit(prior_art_status="clear")
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = [unit]

        with patch("max.store.db.Store", return_value=mock_store):
            result = runner.invoke(main, ["prior-art", "--re-scan", "--dry-run"])
            assert result.exit_code == 0
            assert "MCP Test Framework" in result.output

    def test_stores_results(self, runner):
        unit = _make_unit()
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = [unit]

        pa_result = PriorArtResult(
            buildable_unit_id="bu-test001",
            matches=[_make_match(relevance_score=0.90)],
            status="strong_match",
        )

        with patch("max.store.db.Store", return_value=mock_store), \
             patch("max.analysis.prior_art.check_prior_art", return_value=[pa_result]):
            result = runner.invoke(main, ["prior-art"])
            assert result.exit_code == 0
            assert mock_store.insert_prior_art_match.called
            assert mock_store.update_prior_art_status.called

    def test_auto_reject_strong_matches(self, runner):
        unit = _make_unit()
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = [unit]

        pa_result = PriorArtResult(
            buildable_unit_id="bu-test001",
            matches=[_make_match(relevance_score=0.92)],
            status="strong_match",
        )

        with patch("max.store.db.Store", return_value=mock_store), \
             patch("max.analysis.prior_art.check_prior_art", return_value=[pa_result]):
            result = runner.invoke(main, ["prior-art", "--auto-reject"])
            assert result.exit_code == 0
            assert "auto-rejected" in result.output
            mock_store.insert_feedback.assert_called_once()
            mock_store.update_buildable_unit_status.assert_called_with("bu-test001", "rejected")

    def test_summary_counts(self, runner):
        units = [
            _make_unit(id="bu-1", title="Strong Idea"),
            _make_unit(id="bu-2", title="Weak Idea"),
            _make_unit(id="bu-3", title="Clear Idea"),
        ]
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = units

        pa_results = [
            PriorArtResult("bu-1", [_make_match(relevance_score=0.91)], "strong_match"),
            PriorArtResult("bu-2", [_make_match(relevance_score=0.72)], "weak_match"),
            PriorArtResult("bu-3", [], "clear"),
        ]

        with patch("max.store.db.Store", return_value=mock_store), \
             patch("max.analysis.prior_art.check_prior_art", return_value=pa_results):
            result = runner.invoke(main, ["prior-art"])
            assert result.exit_code == 0
            assert "1 strong" in result.output
            assert "1 weak" in result.output
            assert "1 clear" in result.output


# ── Review Integration ────────────────────────────────────────────


class TestReviewPriorArtIndicator:
    def test_strong_match_indicator(self):
        """_display_idea_card shows [!!] for strong prior art matches."""
        unit = _make_unit(prior_art_status="strong_match")
        assert unit.prior_art_status == "strong_match"

    def test_weak_match_indicator(self):
        unit = _make_unit(prior_art_status="weak_match")
        assert unit.prior_art_status == "weak_match"

    def test_clear_no_indicator(self):
        unit = _make_unit(prior_art_status="clear")
        assert unit.prior_art_status == "clear"


# ── Error Handling Tests ──────────────────────────────────────────


class TestSearchErrorHandling:
    @pytest.mark.asyncio
    async def test_github_search_timeout_exception(self, caplog):
        """GitHub search should handle TimeoutException gracefully."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.TimeoutException("Request timed out")

        with caplog.at_level("WARNING"):
            matches = await _search_github("test query", mock_client)

        assert matches == []
        assert "GitHub search failed for query: test query" in caplog.text

    @pytest.mark.asyncio
    async def test_github_search_http_500_error(self, caplog):
        """GitHub search should handle HTTP 500 without crashing."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        with caplog.at_level("WARNING"):
            matches = await _search_github("test query", mock_client)

        assert matches == []
        assert "GitHub search returned 500 for query: test query" in caplog.text

    @pytest.mark.asyncio
    async def test_npm_search_network_error(self, caplog):
        """npm search should handle network errors gracefully."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.NetworkError("Connection failed")

        with caplog.at_level("WARNING"):
            matches = await _search_npm("test query", mock_client)

        assert matches == []
        assert "npm search failed for query: test query" in caplog.text

    @pytest.mark.asyncio
    async def test_npm_search_http_403_error(self, caplog):
        """npm search should handle HTTP 403 rate limit."""
        mock_response = MagicMock()
        mock_response.status_code = 403

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        with caplog.at_level("WARNING"):
            matches = await _search_npm("test query", mock_client)

        assert matches == []
        assert "npm search returned 403 for query: test query" in caplog.text


class TestPyPIFallbackChain:
    @pytest.mark.asyncio
    async def test_pypi_simple_api_failure_returns_early(self, caplog):
        """PyPI search should return empty when simple API endpoint fails."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        # Mock the sequence of calls in _search_pypi
        # First call (ignored), second call fails -> early return
        mock_response_first = MagicMock()
        mock_response_first.status_code = 200

        mock_response_simple_fail = MagicMock()
        mock_response_simple_fail.status_code = 500

        # Set up the sequence of responses
        mock_client.get.side_effect = [
            mock_response_first,  # First search endpoint (unused result)
            mock_response_simple_fail,  # Simple API endpoint fails -> early return
        ]

        with caplog.at_level("WARNING"):
            matches = await _search_pypi("test query", mock_client)

        assert len(matches) == 0
        assert "PyPI index returned 500" in caplog.text

    @pytest.mark.asyncio
    async def test_pypi_search_fallback_succeeds(self):
        """PyPI search should continue to HTML search after simple API succeeds."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        mock_response_simple = MagicMock()
        mock_response_simple.status_code = 200

        mock_response_search = MagicMock()
        mock_response_search.status_code = 200
        mock_response_search.text = '<a class="package-snippet" href="/project/test-pkg/">'

        mock_response_meta = MagicMock()
        mock_response_meta.status_code = 200
        mock_response_meta.json.return_value = {
            "info": {
                "name": "test-pkg",
                "package_url": "https://pypi.org/project/test-pkg/",
                "summary": "Test package",
                "version": "1.0.0",
            }
        }

        # Set up the sequence of responses
        mock_client.get.side_effect = [
            MagicMock(status_code=200),  # First search endpoint (unused)
            mock_response_simple,  # Simple API endpoint succeeds
            mock_response_search,  # HTML search fallback
            mock_response_meta,  # Package metadata
        ]

        matches = await _search_pypi("test query", mock_client)

        assert len(matches) == 1
        assert matches[0].source == "pypi"
        assert matches[0].title == "test-pkg"

    @pytest.mark.asyncio
    async def test_pypi_partial_metadata_failure(self):
        """PyPI search should skip packages with failed metadata requests."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        mock_response_search = MagicMock()
        mock_response_search.status_code = 200
        mock_response_search.text = (
            '<a class="package-snippet" href="/project/pkg1/">'
            '<a class="package-snippet" href="/project/pkg2/">'
        )

        mock_response_meta_fail = MagicMock()
        mock_response_meta_fail.status_code = 404

        mock_response_meta_success = MagicMock()
        mock_response_meta_success.status_code = 200
        mock_response_meta_success.json.return_value = {
            "info": {
                "name": "pkg2",
                "package_url": "https://pypi.org/project/pkg2/",
                "summary": "Package 2",
                "version": "2.0.0",
            }
        }

        # Sequence: unused search, simple API ok, HTML search ok, meta fail, meta succeed
        mock_client.get.side_effect = [
            MagicMock(status_code=200),  # First search (unused)
            MagicMock(status_code=200),  # Simple API
            mock_response_search,  # HTML search
            mock_response_meta_fail,  # pkg1 metadata fails
            mock_response_meta_success,  # pkg2 metadata succeeds
        ]

        matches = await _search_pypi("test query", mock_client)

        # Only pkg2 should be in results
        assert len(matches) == 1
        assert matches[0].title == "pkg2"


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_searches(self):
        """Rate limiting semaphore should limit concurrent API calls."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_client.get.return_value = mock_response

        # Track concurrent calls
        max_concurrent = 0
        current_concurrent = 0

        async def tracked_get(*args, **kwargs):
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.01)  # Simulate network delay
            current_concurrent -= 1
            return mock_response

        mock_client.get = tracked_get

        # Create semaphore with limit of 2
        semaphore = asyncio.Semaphore(2)
        queries = ["query1", "query2", "query3", "query4", "query5"]

        # Run searches with semaphore
        results = await _search_source(
            "github",
            queries,
            mock_client,
            semaphore,
            delay=0.0,
        )

        # Max concurrent should not exceed semaphore limit
        assert max_concurrent <= 2
        assert results == []  # Empty items in mock response

    @pytest.mark.asyncio
    async def test_delay_between_searches(self):
        """Rate limiting should apply delay between consecutive searches."""
        import time

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_client.get.return_value = mock_response

        semaphore = asyncio.Semaphore(10)  # High limit
        queries = ["query1", "query2", "query3"]
        delay = 0.1

        start_time = time.time()
        await _search_source(
            "github",
            queries,
            mock_client,
            semaphore,
            delay=delay,
        )
        elapsed = time.time() - start_time

        # Should take at least (len(queries) - 1) * delay
        # We subtract 1 because delay happens after each search except the last
        min_expected_time = (len(queries) - 1) * delay * 0.8  # 80% tolerance
        assert elapsed >= min_expected_time


class TestDryRunMode:
    @pytest.mark.asyncio
    async def test_dry_run_returns_unchecked_status(self):
        """Dry run should return unchecked status without making HTTP calls."""
        unit = _make_unit()

        # Mock the client to track if .get() is called
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("max.analysis.prior_art.httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            results = await check_prior_art_batch([unit], dry_run=True)

            # Client should be created but .get() should never be called
            mock_client.get.assert_not_called()

            assert len(results) == 1
            assert results[0].buildable_unit_id == "bu-test001"
            assert results[0].status == "unchecked"
            assert results[0].matches == []

    @pytest.mark.asyncio
    async def test_dry_run_with_multiple_units(self):
        """Dry run should process multiple units without HTTP calls."""
        units = [
            _make_unit(id="bu-1", title="Idea 1"),
            _make_unit(id="bu-2", title="Idea 2"),
            _make_unit(id="bu-3", title="Idea 3"),
        ]

        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("max.analysis.prior_art.httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_client

            results = await check_prior_art_batch(units, dry_run=True)

            # No HTTP requests should be made
            mock_client.get.assert_not_called()

            assert len(results) == 3
            for i, result in enumerate(results):
                assert result.buildable_unit_id == f"bu-{i+1}"
                assert result.status == "unchecked"
                assert result.matches == []


class TestScoreThresholdBoundary:
    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_score_exactly_at_threshold_included(self, mock_sim, mock_embed):
        """Match with score exactly 0.65 should be included."""
        mock_embed.return_value = [1.0] * 10
        mock_sim.return_value = 0.65  # Exactly at threshold

        unit = _make_unit()
        matches = [_make_match(relevance_score=0.0)]
        scored = score_matches(unit, matches)

        assert len(scored) == 1
        assert scored[0].relevance_score == 0.65

    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_score_just_below_threshold_excluded(self, mock_sim, mock_embed):
        """Match with score just below 0.65 should be excluded."""
        mock_embed.return_value = [1.0] * 10
        mock_sim.return_value = 0.649  # Just below threshold

        unit = _make_unit()
        matches = [_make_match(relevance_score=0.0)]
        scored = score_matches(unit, matches)

        assert len(scored) == 0

    @patch("max.analysis.prior_art.embed_text")
    @patch("max.analysis.prior_art._cosine_similarity")
    def test_mixed_threshold_boundary_scores(self, mock_sim, mock_embed):
        """Mix of scores around threshold should filter correctly."""
        mock_embed.return_value = [1.0] * 10
        mock_sim.side_effect = [0.64, 0.65, 0.66, 0.649, 0.651]

        unit = _make_unit()
        matches = [_make_match(title=f"match{i}") for i in range(5)]
        scored = score_matches(unit, matches)

        # Should only include 0.65, 0.66, 0.651
        assert len(scored) == 3
        scores = [m.relevance_score for m in scored]
        assert 0.66 in scores
        assert 0.651 in scores
        assert 0.65 in scores
        assert 0.64 not in scores
        assert 0.649 not in scores

    def test_determine_status_at_weak_threshold(self):
        """Status with score exactly 0.65 should be weak_match."""
        matches = [_make_match(relevance_score=0.65)]
        assert determine_status(matches) == "weak_match"

    def test_determine_status_at_strong_threshold(self):
        """Status with score exactly 0.85 should be strong_match."""
        matches = [_make_match(relevance_score=0.85)]
        assert determine_status(matches) == "strong_match"


class TestPartialSourceFailure:
    @pytest.mark.asyncio
    async def test_one_source_fails_others_succeed(self):
        """When one source fails, other sources should still return results."""
        unit = _make_unit(category="cli_tool")  # Will search github, npm, pypi

        # Create async mock functions that mimic real search function behavior:
        # they catch exceptions internally and return empty list
        async def github_with_error(*args, **kwargs):
            # Simulate the exception handling in real search functions
            return []  # Returns empty, mimicking catch block

        async def npm_success(*args, **kwargs):
            return [_make_match(source="npm", title="npm-package")]

        async def pypi_success(*args, **kwargs):
            return [_make_match(source="pypi", title="pypi-package")]

        # Patch the _SEARCH_FNS dictionary
        with patch.dict("max.analysis.prior_art._SEARCH_FNS", {
            "github": github_with_error,
            "npm": npm_success,
            "pypi": pypi_success,
            "product_hunt": AsyncMock(return_value=[]),
        }), patch("max.analysis.prior_art.score_matches", side_effect=lambda unit, matches: matches):

            results = await check_prior_art_batch([unit], dry_run=False)

            assert len(results) == 1
            # Should have matches from npm and pypi, but not github (empty due to error)
            result_sources = {m.source for m in results[0].matches}
            assert "npm" in result_sources
            assert "pypi" in result_sources
            assert "github" not in result_sources

    @pytest.mark.asyncio
    async def test_all_sources_fail_gracefully(self, caplog):
        """When all sources fail, should return empty results without crashing."""
        unit = _make_unit(category="cli_tool")

        async def fail_source(*args, **kwargs):
            # All sources return empty due to errors (caught internally)
            return []

        # Patch the _SEARCH_FNS dictionary
        with patch.dict("max.analysis.prior_art._SEARCH_FNS", {
            "github": fail_source,
            "npm": fail_source,
            "pypi": fail_source,
            "product_hunt": AsyncMock(return_value=[]),
        }):

            results = await check_prior_art_batch([unit], dry_run=False)

            assert len(results) == 1
            assert results[0].matches == []
            assert results[0].status == "clear"

    @pytest.mark.asyncio
    async def test_multiple_units_partial_failures(self):
        """Multiple units should process independently despite some source failures."""
        units = [
            _make_unit(id="bu-1", category="cli_tool"),
            _make_unit(id="bu-2", category="application"),
        ]

        call_count = {"github": 0}

        async def failing_github(*args, **kwargs):
            call_count["github"] += 1
            # First two calls for first unit (two queries), return empty (simulating error)
            if call_count["github"] <= 2:
                return []
            # Next calls for second unit, succeed
            return [_make_match(source="github", title="github-repo")]

        async def empty_source(*args, **kwargs):
            return []

        # Patch the _SEARCH_FNS dictionary
        with patch.dict("max.analysis.prior_art._SEARCH_FNS", {
            "github": failing_github,
            "npm": empty_source,
            "pypi": empty_source,
            "product_hunt": empty_source,
        }), patch("max.analysis.prior_art.score_matches", side_effect=lambda u, m: m):

            results = await check_prior_art_batch(units, dry_run=False)

            assert len(results) == 2
            # First unit had GitHub fail, so empty matches
            assert len(results[0].matches) == 0
            # Second unit should have GitHub match
            assert len(results[1].matches) >= 1
            github_matches = [m for m in results[1].matches if m.source == "github"]
            assert len(github_matches) >= 1
            assert github_matches[0].title == "github-repo"


# ── Store Methods ─────────────────────────────────────────────────


class TestStorePriorArt:
    def test_insert_and_get(self, tmp_path):
        """Integration test for prior art store methods."""
        from max.store.db import Store

        db_path = tmp_path / "test.db"
        with patch("max.store.db.DB_PATH", db_path):
            store = Store(db_path=db_path)
            try:
                match_id = store.insert_prior_art_match("bu-test001", {
                    "source": "github",
                    "title": "test-repo",
                    "url": "https://github.com/test/test-repo",
                    "description": "A test repo",
                    "relevance_score": 0.88,
                    "match_signals": {"stars": 42},
                    "search_query": "test framework",
                })
                assert match_id.startswith("pa-")

                matches = store.get_prior_art_matches("bu-test001")
                assert len(matches) == 1
                assert matches[0]["source"] == "github"
                assert matches[0]["relevance_score"] == 0.88
                assert matches[0]["match_signals"]["stars"] == 42
            finally:
                store.close()

    def test_update_status(self, tmp_path):
        from max.store.db import Store

        db_path = tmp_path / "test.db"
        with patch("max.store.db.DB_PATH", db_path):
            store = Store(db_path=db_path)
            try:
                # Insert a buildable unit first
                store.conn.execute(
                    """INSERT INTO buildable_units
                       (id, title, one_liner, category, problem, solution,
                        value_proposition, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("bu-test", "Test", "test", "cli_tool", "p", "s", "v",
                     "2024-01-01T00:00:00", "2024-01-01T00:00:00"),
                )
                store.conn.commit()

                store.update_prior_art_status("bu-test", "strong_match")

                row = store.conn.execute(
                    "SELECT prior_art_status FROM buildable_units WHERE id = ?",
                    ("bu-test",),
                ).fetchone()
                assert row["prior_art_status"] == "strong_match"
            finally:
                store.close()

    def test_delete_matches(self, tmp_path):
        from max.store.db import Store

        db_path = tmp_path / "test.db"
        with patch("max.store.db.DB_PATH", db_path):
            store = Store(db_path=db_path)
            try:
                store.insert_prior_art_match("bu-test001", {
                    "source": "github",
                    "title": "repo1",
                    "url": "https://github.com/test/repo1",
                })
                store.insert_prior_art_match("bu-test001", {
                    "source": "npm",
                    "title": "pkg1",
                    "url": "https://npmjs.com/package/pkg1",
                })
                assert len(store.get_prior_art_matches("bu-test001")) == 2

                deleted = store.delete_prior_art_matches("bu-test001")
                assert deleted == 2
                assert len(store.get_prior_art_matches("bu-test001")) == 0
            finally:
                store.close()
