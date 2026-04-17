"""Integration-style smoke tests for CLI entry points.

Tests that each CLI subcommand can be invoked with minimal valid arguments
and completes without unhandled exceptions. Mocks external dependencies
(database, API calls, LLM) so tests run offline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from max.cli import main
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


# ── Fixtures & Helpers ─────────────────────────────────────────────────


@pytest.fixture
def runner() -> CliRunner:
    """Provide a Click test runner."""
    return CliRunner()


def _make_unit(
    id: str = "bu-int001",
    title: str = "Integration Test Idea",
    status: str = "draft",
    domain: str = "devtools",
    category: str = BuildableCategory.CLI_TOOL,
) -> BuildableUnit:
    """Create a minimal BuildableUnit for testing."""
    return BuildableUnit(
        id=id,
        title=title,
        one_liner="Test one-liner",
        category=category,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        target_users="developers",
        value_proposition="Test value prop",
        inspiring_insights=["ins-001"],
        evidence_signals=["sig-001"],
        tech_approach="TypeScript CLI",
        suggested_stack={"language": "typescript"},
        composability_notes="Integrates with CI/CD",
        status=status,
        domain=domain,
    )


def _make_dim(value: float = 7.0, confidence: float = 0.7, reasoning: str = "test") -> DimensionScore:
    """Create a minimal DimensionScore for testing."""
    return DimensionScore(value=value, confidence=confidence, reasoning=reasoning)


def _make_evaluation(unit_id: str = "bu-int001", score: float = 75.0) -> UtilityEvaluation:
    """Create a minimal UtilityEvaluation for testing."""
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_make_dim(8.0),
        addressable_scale=_make_dim(7.0),
        build_effort=_make_dim(7.5),
        composability=_make_dim(8.5),
        competitive_density=_make_dim(9.0),
        timing_fit=_make_dim(8.0),
        compounding_value=_make_dim(7.0),
        overall_score=score,
        strengths=["High demand"],
        weaknesses=["Niche audience"],
        recommendation="yes",
        weights_used={
            "pain_severity": 0.20,
            "addressable_scale": 0.15,
            "build_effort": 0.15,
            "composability": 0.15,
            "competitive_density": 0.10,
            "timing_fit": 0.10,
            "compounding_value": 0.15,
        },
    )


def _make_signal(
    id: str = "sig-int001",
    title: str = "Test Signal",
    has_role: bool = True,
) -> Signal:
    """Create a minimal Signal for testing."""
    metadata = {"signal_role": "problem"} if has_role else {}
    return Signal(
        id=id,
        source_type=SignalSourceType.FORUM,
        source_adapter="hackernews",
        title=title,
        content="Test content",
        url="https://example.com/1",
        credibility=0.7,
        metadata=metadata,
    )


def _mock_store(**overrides) -> MagicMock:
    """Build a mock Store with sensible defaults."""
    store = MagicMock()
    store.get_buildable_units.return_value = overrides.get("units", [])
    store.get_buildable_unit.return_value = overrides.get("unit", None)
    store.get_evaluation.return_value = overrides.get("evaluation", None)
    store.get_feedback_outcomes.return_value = overrides.get("feedback_outcomes", [])
    store.get_signals.return_value = overrides.get("signals", [])
    store.get_feedback_log.return_value = overrides.get("feedback_log", [])
    store.get_prior_art_matches.return_value = overrides.get("prior_art_matches", [])
    store.get_pipeline_runs.return_value = overrides.get("pipeline_runs", [])
    store.has_feedback.return_value = overrides.get("has_feedback", False)
    store.retention_stats.return_value = overrides.get("retention_stats", {})
    store.conn = MagicMock()
    store.conn.execute.return_value.fetchone.return_value = [0]
    store.conn.execute.return_value.rowcount = 0
    store.close.return_value = None
    return store


# ── Integration Tests ──────────────────────────────────────────────────


class TestRunCommand:
    """Integration tests for ``max run``."""

    @patch("max.pipeline.runner.run_pipeline")
    @patch("max.profiles.loader.get_default_profile")
    @patch("max.config.MAX_PROFILE", "")
    def test_run_smoke(self, mock_get_default, mock_run_pipeline, runner: CliRunner) -> None:
        """Smoke test: run command completes without error."""
        from max.pipeline.runner import PipelineResult
        from max.profiles.schema import DomainContext, PipelineProfile

        mock_get_default.return_value = PipelineProfile(
            name="devtools",
            domain=DomainContext(
                name="devtools",
                description="Developer tools",
                categories=["cli_tool"],
                target_user_types=["developers"],
            ),
        )
        mock_run_pipeline.return_value = PipelineResult(
            avg_insight_confidence=0.80,
            avg_idea_score=70.0,
            top_ideas=[],
        )

        result = runner.invoke(main, ["run"])

        assert result.exit_code == 0, result.output
        assert "Running max pipeline" in result.output
        mock_run_pipeline.assert_called_once()

    @patch("max.pipeline.runner.run_pipeline")
    @patch("max.profiles.loader.get_default_profile")
    @patch("max.config.MAX_PROFILE", "")
    def test_run_dry_run(self, mock_get_default, mock_run_pipeline, runner: CliRunner) -> None:
        """Smoke test: run --dry-run completes without error."""
        from max.profiles.schema import DomainContext, PipelineProfile
        from max.types.pipeline import DryRunReport, StageSummary

        mock_get_default.return_value = PipelineProfile(
            name="devtools",
            domain=DomainContext(
                name="devtools",
                description="Developer tools",
                categories=["cli_tool"],
                target_user_types=["developers"],
            ),
        )
        mock_run_pipeline.return_value = DryRunReport(
            stages=[
                StageSummary(
                    name="fetch",
                    would_process=10,
                    estimated_llm_calls=0,
                    skipped=False,
                    reason=None,
                ),
            ],
            estimated_total_llm_calls=20,
            estimated_token_budget=50000,
        )

        result = runner.invoke(main, ["run", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "No changes were made" in result.output


class TestProfilesCommand:
    """Integration tests for ``max profiles``."""

    @patch("max.profiles.loader.list_profiles")
    def test_profiles_empty(self, mock_list, runner: CliRunner) -> None:
        """Smoke test: profiles command with no profiles."""
        mock_list.return_value = []

        result = runner.invoke(main, ["profiles"])

        assert result.exit_code == 0, result.output
        assert "No profiles found" in result.output

    @patch("max.profiles.loader.load_profile")
    @patch("max.profiles.loader.list_profiles")
    def test_profiles_with_profiles(self, mock_list, mock_load, runner: CliRunner) -> None:
        """Smoke test: profiles command lists available profiles."""
        from max.profiles.schema import DomainContext, PipelineProfile

        mock_list.return_value = ["devtools", "healthcare"]
        mock_load.return_value = PipelineProfile(
            name="devtools",
            domain=DomainContext(
                name="devtools",
                description="Developer tools",
                categories=["cli_tool"],
                target_user_types=["developers"],
            ),
            sources=[],
        )

        result = runner.invoke(main, ["profiles"])

        assert result.exit_code == 0, result.output
        assert "Available pipeline profiles" in result.output


class TestIdeasCommand:
    """Integration tests for ``max ideas``."""

    @patch("max.store.db.Store")
    def test_ideas_smoke(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: ideas command completes without error."""
        units = [_make_unit(id="bu-001"), _make_unit(id="bu-002")]
        evaluation = _make_evaluation("bu-001", score=78.0)
        store = _mock_store(units=units)
        store.get_evaluation.side_effect = lambda uid: evaluation if uid == "bu-001" else None
        MockStore.return_value = store

        result = runner.invoke(main, ["ideas"])

        assert result.exit_code == 0, result.output
        store.close.assert_called_once()


class TestInspectCommand:
    """Integration tests for ``max inspect``."""

    @patch("max.store.db.Store")
    def test_inspect_smoke(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: inspect command completes without error."""
        unit = _make_unit()
        evaluation = _make_evaluation()
        store = _mock_store(unit=unit, evaluation=evaluation)
        MockStore.return_value = store

        result = runner.invoke(main, ["inspect", "bu-int001"])

        assert result.exit_code == 0, result.output
        assert "Integration Test Idea" in result.output
        store.close.assert_called_once()


class TestFeedbackCommand:
    """Integration tests for ``max feedback``."""

    @patch("max.store.db.Store")
    def test_feedback_smoke(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: feedback command completes without error."""
        unit = _make_unit()
        store = _mock_store(unit=unit)
        MockStore.return_value = store

        result = runner.invoke(main, ["feedback", "bu-int001", "approved"])

        assert result.exit_code == 0, result.output
        store.insert_feedback.assert_called_once_with("bu-int001", "approved", "")
        store.close.assert_called_once()


class TestTriageCommand:
    """Integration tests for ``max triage``."""

    @patch("max.store.db.Store")
    def test_triage_smoke_no_matches(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: triage command with no matching ideas."""
        store = _mock_store(units=[])
        MockStore.return_value = store

        result = runner.invoke(main, ["triage"])

        assert result.exit_code == 0, result.output
        assert "No ideas found" in result.output

    @patch("max.store.db.Store")
    def test_triage_smoke_with_ideas(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: triage command processes ideas."""
        unit = _make_unit()
        evaluation = _make_evaluation(score=70.0)
        evaluation.recommendation = "yes"
        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = evaluation
        store.has_feedback.return_value = False
        MockStore.return_value = store

        result = runner.invoke(main, ["triage", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output

    @patch("max.store.db.Store")
    def test_triage_smoke_apply(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: triage command applies changes."""
        unit = _make_unit()
        evaluation = _make_evaluation(score=70.0)
        evaluation.recommendation = "yes"
        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = evaluation
        store.has_feedback.return_value = False
        MockStore.return_value = store

        result = runner.invoke(main, ["triage"])

        assert result.exit_code == 0, result.output


class TestDedupCommand:
    """Integration tests for ``max dedup``."""

    @patch("max.store.db.Store")
    def test_dedup_smoke_no_ideas(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: dedup command with no ideas."""
        store = _mock_store(units=[])
        MockStore.return_value = store

        result = runner.invoke(main, ["dedup"])

        assert result.exit_code == 0, result.output
        assert "No ideas found" in result.output

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_dedup_smoke_with_ideas(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Smoke test: dedup command processes ideas."""
        from max.analysis.dedup import IdeaCluster

        unit = _make_unit()
        evaluation = _make_evaluation()
        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = evaluation
        MockStore.return_value = store

        # Mock clustering to return single cluster (no duplicates)
        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit,
                representative_eval=evaluation,
                members=[(unit, evaluation)],
            )
        ]

        result = runner.invoke(main, ["dedup", "--dry-run"])

        assert result.exit_code == 0, result.output


class TestSynthesizeCommand:
    """Integration tests for ``max synthesize``."""

    @patch("max.store.db.Store")
    def test_synthesize_smoke_no_ideas(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: synthesize command with no ideas."""
        store = _mock_store(units=[])
        MockStore.return_value = store

        result = runner.invoke(main, ["synthesize"])

        assert result.exit_code == 0, result.output
        assert "No ideas to synthesize" in result.output

    @patch("max.analysis.dedup.cluster_ideas")
    @patch("max.store.db.Store")
    def test_synthesize_smoke_dry_run(self, MockStore, mock_cluster, runner: CliRunner) -> None:
        """Smoke test: synthesize --dry-run completes without LLM calls."""
        from max.analysis.dedup import IdeaCluster

        unit1 = _make_unit(id="bu-001", title="Idea 1")
        unit2 = _make_unit(id="bu-002", title="Idea 2")
        eval1 = _make_evaluation("bu-001", score=75.0)
        eval2 = _make_evaluation("bu-002", score=72.0)
        store = _mock_store(units=[unit1, unit2])
        store.get_evaluation.side_effect = lambda uid: eval1 if uid == "bu-001" else eval2
        MockStore.return_value = store

        # Mock clustering to return a multi-member cluster
        mock_cluster.return_value = [
            IdeaCluster(
                representative=unit1,
                representative_eval=eval1,
                members=[(unit1, eval1), (unit2, eval2)],
            )
        ]

        result = runner.invoke(main, ["synthesize", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "Dry run" in result.output


class TestPriorArtCommand:
    """Integration tests for ``max prior-art``."""

    @patch("max.store.db.Store")
    def test_prior_art_smoke_no_ideas(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: prior-art command with no ideas."""
        store = _mock_store(units=[])
        MockStore.return_value = store

        result = runner.invoke(main, ["prior-art"])

        assert result.exit_code == 0, result.output
        assert "No ideas to check" in result.output

    @patch("max.analysis.prior_art.build_search_queries")
    @patch("max.analysis.prior_art.select_sources")
    @patch("max.store.db.Store")
    def test_prior_art_smoke_dry_run(self, MockStore, mock_sources, mock_queries, runner: CliRunner) -> None:
        """Smoke test: prior-art --dry-run completes without API calls."""
        unit = _make_unit()
        unit.prior_art_status = "unchecked"
        store = _mock_store(units=[unit])
        MockStore.return_value = store
        mock_queries.return_value = ["test query"]
        mock_sources.return_value = ["github"]

        result = runner.invoke(main, ["prior-art", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "Dry run" in result.output


class TestReviewCommand:
    """Integration tests for ``max review``."""

    @patch("max.store.db.Store")
    def test_review_smoke_no_ideas(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: review command with no ideas."""
        store = _mock_store(units=[])
        MockStore.return_value = store

        result = runner.invoke(main, ["review"])

        assert result.exit_code == 0, result.output
        assert "No ideas found" in result.output

    @patch("max.store.db.Store")
    def test_review_smoke_all_have_feedback(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: review command when all ideas have feedback."""
        unit = _make_unit()
        evaluation = _make_evaluation()
        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = evaluation
        store.has_feedback.return_value = True
        MockStore.return_value = store

        result = runner.invoke(main, ["review"])

        assert result.exit_code == 0, result.output
        assert "No ideas pending review" in result.output


class TestFeedbackLogCommand:
    """Integration tests for ``max feedback-log``."""

    @patch("max.store.db.Store")
    def test_feedback_log_smoke_empty(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: feedback-log command with no records."""
        store = _mock_store(feedback_log=[])
        MockStore.return_value = store

        result = runner.invoke(main, ["feedback-log"])

        assert result.exit_code == 0, result.output
        assert "No feedback recorded yet" in result.output

    @patch("max.store.db.Store")
    def test_feedback_log_smoke_with_records(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: feedback-log command displays records."""
        feedback_log = [
            {
                "outcome": "approved",
                "score": 75.0,
                "domain": "devtools",
                "title": "Test Idea",
                "reason": "Good fit",
            }
        ]
        store = _mock_store(feedback_log=feedback_log)
        MockStore.return_value = store

        result = runner.invoke(main, ["feedback-log"])

        assert result.exit_code == 0, result.output
        assert "approved" in result.output


class TestAdaptWeightsCommand:
    """Integration tests for ``max adapt-weights``."""

    @patch("max.store.db.Store")
    def test_adapt_weights_smoke_no_feedback(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: adapt-weights command with no feedback."""
        store = _mock_store(feedback_outcomes=[])
        MockStore.return_value = store

        result = runner.invoke(main, ["adapt-weights"])

        assert result.exit_code == 0, result.output
        assert "No feedback recorded" in result.output

    @patch("max.evaluation.weights.adapt_weights")
    @patch("max.evaluation.weights.get_weights")
    @patch("max.store.db.Store")
    def test_adapt_weights_smoke_with_feedback(self, MockStore, mock_get_w, mock_adapt, runner: CliRunner) -> None:
        """Smoke test: adapt-weights command with feedback."""
        outcomes = [{"unit_id": "bu-001", "outcome": "approved", "success": True}]
        store = _mock_store(feedback_outcomes=outcomes)
        MockStore.return_value = store

        base = {"pain_severity": 0.20, "addressable_scale": 0.15}
        adapted = {"pain_severity": 0.22, "addressable_scale": 0.14}
        mock_get_w.return_value = base
        mock_adapt.return_value = adapted

        result = runner.invoke(main, ["adapt-weights"])

        assert result.exit_code == 0, result.output
        assert "Adapted weights" in result.output


class TestBackfillRolesCommand:
    """Integration tests for ``max backfill-roles``."""

    @patch("max.store.db.Store")
    def test_backfill_roles_smoke_all_classified(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: backfill-roles when all signals have roles."""
        sig = _make_signal(has_role=True)
        store = _mock_store(signals=[sig])
        MockStore.return_value = store

        result = runner.invoke(main, ["backfill-roles"])

        assert result.exit_code == 0, result.output
        assert "All signals already have roles" in result.output

    @patch("max.analysis.roles.classify_signal_role")
    @patch("max.store.db.Store")
    def test_backfill_roles_smoke_processes_signals(self, MockStore, mock_classify, runner: CliRunner) -> None:
        """Smoke test: backfill-roles processes unclassified signals."""
        sig = _make_signal(has_role=False)
        store = _mock_store(signals=[sig])
        MockStore.return_value = store
        mock_classify.return_value = "problem"

        result = runner.invoke(main, ["backfill-roles"])

        assert result.exit_code == 0, result.output
        assert "Backfilling" in result.output
        assert "Done" in result.output


class TestSummaryCommand:
    """Integration tests for ``max summary``."""

    @patch("max.store.db.Store")
    def test_summary_smoke_no_ideas(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: summary command with no ideas."""
        store = _mock_store(units=[])
        MockStore.return_value = store

        result = runner.invoke(main, ["summary"])

        assert result.exit_code == 0, result.output
        assert "No ideas found" in result.output

    @patch("max.store.db.Store")
    def test_summary_smoke_with_ideas(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: summary command displays domain summary."""
        unit = _make_unit(domain="devtools")
        evaluation = _make_evaluation()
        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = evaluation
        MockStore.return_value = store

        result = runner.invoke(main, ["summary"])

        assert result.exit_code == 0, result.output
        assert "devtools" in result.output
        assert "TOTAL" in result.output


class TestTrendsCommand:
    """Integration tests for ``max trends``."""

    @patch("max.store.db.Store")
    def test_trends_smoke_no_data(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: trends command with no pipeline runs."""
        from max.analysis.retrospective import detect_trends

        with patch("max.analysis.retrospective.detect_trends") as mock_detect:
            mock_detect.return_value = []
            store = _mock_store()
            MockStore.return_value = store

            result = runner.invoke(main, ["trends"])

            assert result.exit_code == 0, result.output
            assert "Not enough pipeline runs" in result.output

    @patch("max.store.db.Store")
    def test_trends_smoke_with_data(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: trends command displays trend data."""
        from max.analysis.retrospective import TrendPoint, detect_trends

        with patch("max.analysis.retrospective.detect_trends") as mock_detect:
            now = datetime.now(timezone.utc)
            mock_detect.return_value = [
                TrendPoint(
                    window_start=now,
                    window_end=now,
                    approval_rate=0.5,
                    avg_score=70.0,
                    signal_count=10,
                    trend_direction="stable",
                )
            ]
            store = _mock_store()
            MockStore.return_value = store

            result = runner.invoke(main, ["trends"])

            assert result.exit_code == 0, result.output
            assert "stable" in result.output


class TestBackfillDomainsCommand:
    """Integration tests for ``max backfill-domains``."""

    @patch("max.store.db.Store")
    def test_backfill_domains_smoke_no_runs(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: backfill-domains with no pipeline runs."""
        store = _mock_store(pipeline_runs=[])
        MockStore.return_value = store

        result = runner.invoke(main, ["backfill-domains"])

        assert result.exit_code == 0, result.output
        assert "No pipeline runs" in result.output

    @patch("max.store.db.Store")
    def test_backfill_domains_smoke_with_runs(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: backfill-domains processes pipeline runs."""
        pipeline_runs = [
            {
                "ideas_generated": 5,
                "config": {"profile": "devtools"},
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T01:00:00Z",
            }
        ]
        store = _mock_store(pipeline_runs=pipeline_runs)
        MockStore.return_value = store

        result = runner.invoke(main, ["backfill-domains"])

        assert result.exit_code == 0, result.output


class TestArchiveCommand:
    """Integration tests for ``max archive``."""

    @patch("max.store.db.Store")
    def test_archive_smoke_dry_run(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: archive --dry-run completes without modifying data."""
        retention_stats = {
            "signals": {"total": 100, "active": 90, "archived": 10},
            "insights": {"total": 50, "active": 45, "archived": 5},
            "pipeline_runs": {"total": 20, "active": 18, "archived": 2},
        }
        store = _mock_store(retention_stats=retention_stats)
        MockStore.return_value = store

        result = runner.invoke(main, ["archive", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "DRY RUN" in result.output
        assert "Run without --dry-run to apply changes" in result.output

    @patch("max.store.db.Store")
    def test_archive_smoke_apply(self, MockStore, runner: CliRunner) -> None:
        """Smoke test: archive command archives old records."""
        retention_stats = {
            "signals": {"total": 100, "active": 90, "archived": 10},
        }
        store = _mock_store(retention_stats=retention_stats)
        store.archive_old_records.return_value = {
            "signals_archived": 5,
            "insights_archived": 2,
            "runs_archived": 1,
        }
        MockStore.return_value = store

        result = runner.invoke(main, ["archive", "--days", "90"])

        assert result.exit_code == 0, result.output
        store.archive_old_records.assert_called_once()


class TestServeCommand:
    """Integration tests for ``max serve``."""

    @patch("uvicorn.run")
    @patch("max.config.MAX_HOST", "0.0.0.0")
    @patch("max.config.MAX_PORT", 8000)
    def test_serve_smoke(self, mock_uvicorn_run, runner: CliRunner) -> None:
        """Smoke test: serve command starts server."""
        result = runner.invoke(main, ["serve"])

        assert result.exit_code == 0, result.output
        assert "Starting max server" in result.output
        mock_uvicorn_run.assert_called_once()

    @patch("uvicorn.run")
    @patch("max.config.MAX_HOST", "0.0.0.0")
    @patch("max.config.MAX_PORT", 8000)
    def test_serve_smoke_custom_options(self, mock_uvicorn_run, runner: CliRunner) -> None:
        """Smoke test: serve command with custom host/port."""
        result = runner.invoke(main, ["serve", "--host", "127.0.0.1", "--port", "9000", "--reload"])

        assert result.exit_code == 0, result.output
        call_kwargs = mock_uvicorn_run.call_args.kwargs
        assert call_kwargs["host"] == "127.0.0.1"
        assert call_kwargs["port"] == 9000
        assert call_kwargs["reload"] is True
