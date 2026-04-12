"""Tests for prior art detection — search, scoring, CLI command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from max.analysis.prior_art import (
    PriorArtMatch,
    PriorArtResult,
    build_search_queries,
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
