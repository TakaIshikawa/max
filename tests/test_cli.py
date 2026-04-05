"""Tests for the CLI interface (max.cli).

All CLI commands use lazy (in-function) imports, so patches target the
source modules (e.g. ``max.store.db.Store``) rather than ``max.cli.Store``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from max.cli import main
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType
from max.types.tact_spec import (
    TactArchitecture,
    TactGoal,
    TactProduct,
    TactRequirement,
    TactSpec,
    TactTechStack,
)


# ── Helpers ────────────────────────────────────────────────────────


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _make_unit(
    id: str = "bu-test001",
    title: str = "MCP Test Framework",
    status: str = "draft",
    category: str = BuildableCategory.CLI_TOOL,
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
    )


def _make_dim(value: float = 7.0, confidence: float = 0.7, reasoning: str = "test") -> DimensionScore:
    return DimensionScore(value=value, confidence=confidence, reasoning=reasoning)


def _make_evaluation(unit_id: str = "bu-test001", score: float = 78.0) -> UtilityEvaluation:
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
        strengths=["High demand", "Low competition"],
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


def _make_tact_spec(unit_id: str = "bu-test001") -> TactSpec:
    return TactSpec(
        buildable_unit_id=unit_id,
        product=TactProduct(
            name="mcp-test-framework",
            vision="Standardized testing for MCP servers",
            goals=[
                TactGoal(
                    id="G-1",
                    description="Validate MCP server protocol compliance",
                    success_criteria="100% of MCP protocol methods covered",
                ),
            ],
            tech_stack=TactTechStack(
                languages=["TypeScript"],
                frameworks=["Node.js"],
                infrastructure=["npm"],
            ),
            constraints=["MVP: protocol validation only"],
        ),
        architecture=TactArchitecture(
            patterns=[],
            invariants=["All tests must be deterministic"],
            conventions=["kebab-case file names"],
        ),
        requirements=[
            TactRequirement(
                title="Implement protocol validator",
                priority="critical",
                description="Core protocol validation engine",
                acceptance_criteria=["Validates initialize handshake"],
            ),
        ],
    )


def _mock_store(**overrides) -> MagicMock:
    """Build a mock Store with sensible defaults. Override individual methods via kwargs."""
    store = MagicMock()
    store.get_buildable_units.return_value = overrides.get("units", [])
    store.get_buildable_unit.return_value = overrides.get("unit", None)
    store.get_evaluation.return_value = overrides.get("evaluation", None)
    store.get_tact_spec.return_value = overrides.get("tact_spec", None)
    store.get_feedback_outcomes.return_value = overrides.get("feedback_outcomes", [])
    store.get_signals.return_value = overrides.get("signals", [])
    store.close.return_value = None
    return store


# ── run command ────────────────────────────────────────────────────


class TestRunCommand:
    """Tests for ``max run``."""

    @patch("max.pipeline.runner.run_pipeline")
    @patch("max.profiles.loader.get_default_profile")
    @patch("max.config.MAX_PROFILE", "")
    def test_run_defaults(self, mock_get_default, mock_run_pipeline, runner: CliRunner) -> None:
        """Running without flags uses default profile and passes it to run_pipeline."""
        from max.pipeline.runner import PipelineResult
        from max.profiles.schema import DomainContext, PipelineProfile

        mock_profile = PipelineProfile(
            name="devtools",
            domain=DomainContext(
                name="devtools",
                description="Developer tools",
                categories=["cli_tool"],
                target_user_types=["developers"],
            ),
            signal_limit=30,
            ideation_mode="direct",
        )
        mock_get_default.return_value = mock_profile
        mock_run_pipeline.return_value = PipelineResult(
            signals_fetched=10,
            signals_new=5,
            signals_skipped=5,
            insights_generated=3,
            ideas_generated=2,
            ideas_evaluated=2,
            specs_generated=1,
            avg_insight_confidence=0.80,
            avg_idea_score=72.5,
            top_ideas=[{"title": "Test Idea", "score": 75.0, "recommendation": "yes"}],
        )

        result = runner.invoke(main, ["run"])

        assert result.exit_code == 0, result.output
        assert "Running max pipeline" in result.output
        mock_run_pipeline.assert_called_once()
        call_kwargs = mock_run_pipeline.call_args
        assert call_kwargs.kwargs["profile"] is mock_profile

    @patch("max.pipeline.runner.run_pipeline")
    @patch("max.profiles.loader.load_profile")
    @patch("max.config.MAX_PROFILE", "")
    def test_run_with_profile_flag(self, mock_load, mock_run_pipeline, runner: CliRunner) -> None:
        """--profile flag loads the named profile."""
        from max.pipeline.runner import PipelineResult
        from max.profiles.schema import DomainContext, PipelineProfile

        mock_profile = PipelineProfile(
            name="healthcare",
            domain=DomainContext(
                name="healthcare",
                description="Healthcare tech",
                categories=["clinical_tool"],
                target_user_types=["clinicians"],
            ),
        )
        mock_load.return_value = mock_profile
        mock_run_pipeline.return_value = PipelineResult(
            avg_insight_confidence=0.80,
            avg_idea_score=70.0,
            top_ideas=[],
        )

        result = runner.invoke(main, ["run", "--profile", "healthcare"])

        assert result.exit_code == 0, result.output
        mock_load.assert_called_once_with("healthcare")

    @patch("max.pipeline.runner.run_pipeline")
    @patch("max.profiles.loader.get_default_profile")
    @patch("max.config.MAX_PROFILE", "")
    def test_run_cli_overrides(self, mock_get_default, mock_run_pipeline, runner: CliRunner) -> None:
        """CLI flags override profile values."""
        from max.pipeline.runner import PipelineResult
        from max.profiles.schema import DomainContext, PipelineProfile

        mock_profile = PipelineProfile(
            name="devtools",
            domain=DomainContext(
                name="devtools",
                description="Developer tools",
                categories=["cli_tool"],
                target_user_types=["developers"],
            ),
            signal_limit=30,
            ideation_mode="direct",
        )
        mock_get_default.return_value = mock_profile
        mock_run_pipeline.return_value = PipelineResult(
            avg_insight_confidence=0.80,
            avg_idea_score=70.0,
            top_ideas=[],
        )

        result = runner.invoke(main, [
            "run",
            "--signal-limit", "50",
            "--min-score", "60.0",
            "--weight-profile", "moonshots",
            "--mode", "cross_domain",
            "--output", "/tmp/test-output",
        ])

        assert result.exit_code == 0, result.output
        # The profile object should have been mutated before passing to run_pipeline
        assert mock_profile.signal_limit == 50
        assert mock_profile.evaluation.min_score == 60.0
        assert mock_profile.evaluation.weight_profile == "moonshots"
        assert mock_profile.ideation_mode == "cross_domain"
        # Output dir passed explicitly
        call_kwargs = mock_run_pipeline.call_args.kwargs
        assert call_kwargs["output_dir"] == Path("/tmp/test-output")

    @patch("max.pipeline.runner.run_pipeline")
    @patch("max.profiles.loader.get_default_profile")
    @patch("max.config.MAX_PROFILE", "")
    def test_run_output_displays_results(self, mock_get_default, mock_run_pipeline, runner: CliRunner) -> None:
        """Verify result summary is printed."""
        from max.pipeline.runner import PipelineResult
        from max.profiles.schema import DomainContext, PipelineProfile

        mock_get_default.return_value = PipelineProfile(
            name="devtools",
            domain=DomainContext(
                name="devtools", description="Dev", categories=["cli_tool"], target_user_types=["devs"],
            ),
        )
        mock_run_pipeline.return_value = PipelineResult(
            signals_fetched=10,
            signals_new=8,
            signals_skipped=2,
            insights_generated=3,
            insights_duplicates_skipped=1,
            ideas_generated=2,
            ideas_duplicates_skipped=0,
            ideas_evaluated=2,
            specs_generated=1,
            avg_insight_confidence=0.85,
            avg_idea_score=72.5,
            top_ideas=[
                {"title": "Cool Idea", "score": 80.0, "recommendation": "yes"},
                {"title": "Meh Idea", "score": 40.0, "recommendation": "no"},
            ],
            token_usage={"total": 5000, "total_input": 3000, "total_output": 2000},
        )

        result = runner.invoke(main, ["run"])

        assert result.exit_code == 0, result.output
        assert "Signals fetched:    10" in result.output
        assert "Insights generated: 3" in result.output
        assert "Ideas generated:    2" in result.output
        assert "Specs generated:    1" in result.output
        assert "Token usage:" in result.output
        assert "Top ideas:" in result.output
        assert "Cool Idea" in result.output


# ── ideas command ──────────────────────────────────────────────────


class TestIdeasCommand:
    """Tests for ``max ideas``."""

    @patch("max.store.db.Store")
    def test_ideas_empty(self, MockStore, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(units=[])
        result = runner.invoke(main, ["ideas"])
        assert result.exit_code == 0
        assert "No ideas found" in result.output

    @patch("max.store.db.Store")
    def test_ideas_with_evaluations(self, MockStore, runner: CliRunner) -> None:
        units = [_make_unit(id="bu-001", title="Idea Alpha"), _make_unit(id="bu-002", title="Idea Beta")]
        evaluation = _make_evaluation("bu-001", score=78.0)
        store = _mock_store(units=units)
        store.get_evaluation.side_effect = lambda uid: evaluation if uid == "bu-001" else None
        MockStore.return_value = store

        result = runner.invoke(main, ["ideas"])

        assert result.exit_code == 0
        assert "Idea Alpha" in result.output
        assert "Idea Beta" in result.output
        assert "78.0" in result.output
        # bu-002 has no evaluation → score 0.0
        assert "0.0" in result.output
        store.close.assert_called_once()

    @patch("max.store.db.Store")
    def test_ideas_status_filter(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(units=[])
        MockStore.return_value = store

        runner.invoke(main, ["ideas", "--status", "approved"])

        store.get_buildable_units.assert_called_once_with(limit=20, status="approved", domain=None)

    @patch("max.store.db.Store")
    def test_ideas_limit(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(units=[])
        MockStore.return_value = store

        runner.invoke(main, ["ideas", "--limit", "5"])

        store.get_buildable_units.assert_called_once_with(limit=5, status=None, domain=None)


# ── inspect command ────────────────────────────────────────────────


class TestInspectCommand:
    """Tests for ``max inspect``."""

    @patch("max.store.db.Store")
    def test_inspect_not_found(self, MockStore, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(unit=None)
        result = runner.invoke(main, ["inspect", "bu-nonexistent"])
        assert result.exit_code == 0
        assert "Not found: bu-nonexistent" in result.output

    @patch("max.store.db.Store")
    def test_inspect_with_evaluation(self, MockStore, runner: CliRunner) -> None:
        unit = _make_unit()
        evaluation = _make_evaluation()
        store = _mock_store(unit=unit, evaluation=evaluation)
        MockStore.return_value = store

        result = runner.invoke(main, ["inspect", "bu-test001"])

        assert result.exit_code == 0
        assert "Title:       MCP Test Framework" in result.output
        assert "One-liner:" in result.output
        assert "Category:    cli_tool" in result.output
        assert "Status:      draft" in result.output
        assert "Problem:" in result.output
        assert "Solution:" in result.output
        assert "Overall Score: 78.0" in result.output
        assert "Recommendation: yes" in result.output
        assert "pain_severity" in result.output
        assert "Strengths:" in result.output
        assert "High demand" in result.output
        assert "Weaknesses:" in result.output
        assert "Niche audience" in result.output
        store.close.assert_called_once()

    @patch("max.store.db.Store")
    def test_inspect_without_evaluation(self, MockStore, runner: CliRunner) -> None:
        unit = _make_unit()
        store = _mock_store(unit=unit, evaluation=None)
        MockStore.return_value = store

        result = runner.invoke(main, ["inspect", "bu-test001"])

        assert result.exit_code == 0
        assert "Title:       MCP Test Framework" in result.output
        assert "Overall Score" not in result.output


# ── publish command ────────────────────────────────────────────────


class TestPublishCommand:
    """Tests for ``max publish``."""

    @patch("max.store.db.Store")
    def test_publish_not_found(self, MockStore, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(unit=None)
        result = runner.invoke(main, ["publish", "bu-nonexistent"])
        assert result.exit_code == 0
        assert "Not found: bu-nonexistent" in result.output

    @patch("max.store.db.Store")
    def test_publish_no_evaluation(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(unit=_make_unit(), evaluation=None)
        MockStore.return_value = store

        result = runner.invoke(main, ["publish", "bu-test001"])

        assert result.exit_code == 0
        assert "No evaluation for bu-test001" in result.output

    @patch("max.publisher.file_writer.write_tact_spec")
    @patch("max.spec.generator.generate_spec")
    @patch("max.store.db.Store")
    def test_publish_generates_and_writes(self, MockStore, mock_gen, mock_write, runner: CliRunner) -> None:
        unit = _make_unit()
        evaluation = _make_evaluation()
        spec = _make_tact_spec()

        store = _mock_store(unit=unit, evaluation=evaluation, tact_spec=None)
        MockStore.return_value = store
        mock_gen.return_value = spec

        result = runner.invoke(main, ["publish", "bu-test001", "--output", "/tmp/specs"])

        assert result.exit_code == 0, result.output
        mock_gen.assert_called_once_with(unit, evaluation)
        store.insert_tact_spec.assert_called_once_with(spec)
        mock_write.assert_called_once()
        write_call_args = mock_write.call_args
        assert write_call_args[0][0] is spec
        assert "mcp-test-framework" in str(write_call_args[0][1])
        store.update_buildable_unit_status.assert_called_once_with("bu-test001", "published")

    @patch("max.publisher.file_writer.write_tact_spec")
    @patch("max.spec.generator.generate_spec")
    @patch("max.store.db.Store")
    def test_publish_uses_existing_spec(self, MockStore, mock_gen, mock_write, runner: CliRunner) -> None:
        """When spec already exists in DB, skip generation."""
        spec = _make_tact_spec()
        store = _mock_store(unit=_make_unit(), evaluation=_make_evaluation(), tact_spec=spec)
        MockStore.return_value = store

        result = runner.invoke(main, ["publish", "bu-test001"])

        assert result.exit_code == 0
        assert "Using existing spec" in result.output
        mock_gen.assert_not_called()

    @patch("max.spec.generator.generate_spec")
    @patch("max.store.db.Store")
    def test_publish_dry_run(self, MockStore, mock_gen, runner: CliRunner) -> None:
        spec = _make_tact_spec()
        store = _mock_store(unit=_make_unit(), evaluation=_make_evaluation(), tact_spec=None)
        MockStore.return_value = store
        mock_gen.return_value = spec

        result = runner.invoke(main, ["publish", "bu-test001", "--dry-run"])

        assert result.exit_code == 0
        assert "mcp-test-framework" in result.output
        store.update_buildable_unit_status.assert_not_called()


# ── feedback command ───────────────────────────────────────────────


class TestFeedbackCommand:
    """Tests for ``max feedback``."""

    @patch("max.store.db.Store")
    def test_feedback_not_found(self, MockStore, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(unit=None)
        result = runner.invoke(main, ["feedback", "bu-missing", "approved"])
        assert result.exit_code == 0
        assert "Not found: bu-missing" in result.output

    @pytest.mark.parametrize("outcome", ["approved", "rejected", "published", "abandoned"])
    @patch("max.store.db.Store")
    def test_feedback_valid_outcomes(self, MockStore, outcome: str, runner: CliRunner) -> None:
        unit = _make_unit()
        store = _mock_store(unit=unit)
        MockStore.return_value = store

        result = runner.invoke(main, ["feedback", "bu-test001", outcome])

        assert result.exit_code == 0
        store.insert_feedback.assert_called_once_with("bu-test001", outcome, "")
        store.update_buildable_unit_status.assert_called_once_with("bu-test001", outcome)
        assert f"Recorded: MCP Test Framework" in result.output
        store.close.assert_called_once()

    @patch("max.store.db.Store")
    def test_feedback_with_reason(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(unit=_make_unit())
        MockStore.return_value = store

        result = runner.invoke(main, ["feedback", "bu-test001", "rejected", "-r", "Too niche"])

        assert result.exit_code == 0
        store.insert_feedback.assert_called_once_with("bu-test001", "rejected", "Too niche")

    def test_feedback_invalid_outcome(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["feedback", "bu-test001", "invalid"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output


# ── adapt_weights command ──────────────────────────────────────────


class TestAdaptWeightsCommand:
    """Tests for ``max adapt-weights``."""

    @patch("max.store.db.Store")
    def test_adapt_no_feedback(self, MockStore, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(feedback_outcomes=[])

        result = runner.invoke(main, ["adapt-weights"])

        assert result.exit_code == 0
        assert "No feedback recorded" in result.output

    @patch("max.evaluation.weights.save_weights")
    @patch("max.evaluation.weights.adapt_weights")
    @patch("max.evaluation.weights.get_weights")
    @patch("max.store.db.Store")
    def test_adapt_with_feedback(self, MockStore, mock_get_w, mock_adapt, mock_save, runner: CliRunner) -> None:
        outcomes = [{"unit_id": "bu-001", "outcome": "approved"}]
        MockStore.return_value = _mock_store(feedback_outcomes=outcomes)

        base = {"pain_severity": 0.20, "addressable_scale": 0.15}
        adapted = {"pain_severity": 0.22, "addressable_scale": 0.14}
        mock_get_w.return_value = base
        mock_adapt.return_value = adapted

        result = runner.invoke(main, ["adapt-weights"])

        assert result.exit_code == 0, result.output
        mock_get_w.assert_called_once_with("default")
        mock_adapt.assert_called_once_with(outcomes, base)
        assert "pain_severity" in result.output
        assert "Adapted weights from 1 feedback" in result.output

    @patch("max.evaluation.weights.save_weights")
    @patch("max.evaluation.weights.adapt_weights")
    @patch("max.evaluation.weights.get_weights")
    @patch("max.store.db.Store")
    def test_adapt_with_save(self, MockStore, mock_get_w, mock_adapt, mock_save, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(feedback_outcomes=[{"unit_id": "bu-001", "outcome": "approved"}])
        mock_get_w.return_value = {"pain_severity": 0.20}
        mock_adapt.return_value = {"pain_severity": 0.22}

        result = runner.invoke(main, ["adapt-weights", "--save", "/tmp/weights.json"])

        assert result.exit_code == 0, result.output
        mock_save.assert_called_once_with({"pain_severity": 0.22}, Path("/tmp/weights.json"))
        assert "Saved to: /tmp/weights.json" in result.output

    @patch("max.evaluation.weights.save_weights")
    @patch("max.evaluation.weights.adapt_weights")
    @patch("max.evaluation.weights.get_weights")
    @patch("max.store.db.Store")
    def test_adapt_custom_base_profile(self, MockStore, mock_get_w, mock_adapt, mock_save, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(feedback_outcomes=[{"unit_id": "bu-001", "outcome": "approved"}])
        mock_get_w.return_value = {"pain_severity": 0.30}
        mock_adapt.return_value = {"pain_severity": 0.32}

        result = runner.invoke(main, ["adapt-weights", "--base-profile", "moonshots"])

        assert result.exit_code == 0, result.output
        mock_get_w.assert_called_once_with("moonshots")


# ── backfill_roles command ─────────────────────────────────────────


class TestBackfillRolesCommand:
    """Tests for ``max backfill-roles``."""

    @patch("max.store.db.Store")
    def test_backfill_all_classified(self, MockStore, runner: CliRunner) -> None:
        sig = Signal(
            id="sig-001",
            source_type=SignalSourceType.FORUM,
            source_adapter="hackernews",
            title="Test",
            content="Content",
            url="https://example.com/1",
            credibility=0.7,
            metadata={"signal_role": "problem"},
        )
        MockStore.return_value = _mock_store(signals=[sig])

        result = runner.invoke(main, ["backfill-roles"])

        assert result.exit_code == 0
        assert "All signals already have roles" in result.output

    @patch("max.analysis.roles.classify_signal_role")
    @patch("max.store.db.Store")
    def test_backfill_processes_unclassified(self, MockStore, mock_classify, runner: CliRunner) -> None:
        sig1 = Signal(
            id="sig-001",
            source_type=SignalSourceType.FORUM,
            source_adapter="hackernews",
            title="Test 1",
            content="Content 1",
            url="https://example.com/1",
            credibility=0.7,
            metadata={},
        )
        sig2 = Signal(
            id="sig-002",
            source_type=SignalSourceType.REGISTRY,
            source_adapter="npm_registry",
            title="Test 2",
            content="Content 2",
            url="https://example.com/2",
            credibility=0.6,
            metadata={},
        )
        store = _mock_store(signals=[sig1, sig2])
        MockStore.return_value = store
        mock_classify.side_effect = ["problem", "solution"]

        result = runner.invoke(main, ["backfill-roles"])

        assert result.exit_code == 0
        assert "Backfilling 2 unclassified signals" in result.output
        assert mock_classify.call_count == 2
        assert store.update_signal_role.call_count == 2
        store.update_signal_role.assert_any_call("sig-001", "problem")
        store.update_signal_role.assert_any_call("sig-002", "solution")
        assert "problem" in result.output
        assert "solution" in result.output
        assert "Done." in result.output


# ── serve command ──────────────────────────────────────────────────


class TestServeCommand:
    """Tests for ``max serve``."""

    @patch("uvicorn.run")
    @patch("max.config.MAX_HOST", "0.0.0.0")
    @patch("max.config.MAX_PORT", 8000)
    def test_serve_defaults(self, mock_uvicorn_run, runner: CliRunner) -> None:
        result = runner.invoke(main, ["serve"])

        assert result.exit_code == 0, result.output
        mock_uvicorn_run.assert_called_once_with(
            "max.server.app:create_app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            factory=True,
        )
        assert "Starting max server on 0.0.0.0:8000" in result.output

    @patch("uvicorn.run")
    @patch("max.config.MAX_HOST", "0.0.0.0")
    @patch("max.config.MAX_PORT", 8000)
    def test_serve_custom_host_port(self, mock_uvicorn_run, runner: CliRunner) -> None:
        result = runner.invoke(main, ["serve", "--host", "127.0.0.1", "--port", "9000"])

        assert result.exit_code == 0, result.output
        mock_uvicorn_run.assert_called_once_with(
            "max.server.app:create_app",
            host="127.0.0.1",
            port=9000,
            reload=False,
            factory=True,
        )

    @patch("uvicorn.run")
    @patch("max.config.MAX_HOST", "0.0.0.0")
    @patch("max.config.MAX_PORT", 8000)
    def test_serve_reload(self, mock_uvicorn_run, runner: CliRunner) -> None:
        result = runner.invoke(main, ["serve", "--reload"])

        assert result.exit_code == 0, result.output
        call_kwargs = mock_uvicorn_run.call_args
        assert call_kwargs.kwargs["reload"] is True

    @patch("uvicorn.run")
    @patch("max.config.MAX_HOST", "0.0.0.0")
    @patch("max.config.MAX_PORT", 8000)
    def test_serve_schedule_interval_sets_env(self, mock_uvicorn_run, runner: CliRunner) -> None:
        result = runner.invoke(main, ["serve", "--schedule-interval", "3600"])

        assert result.exit_code == 0, result.output
        assert "every 3600s" in result.output

    @patch("uvicorn.run")
    @patch("max.config.MAX_HOST", "0.0.0.0")
    @patch("max.config.MAX_PORT", 8000)
    def test_serve_no_schedule(self, mock_uvicorn_run, runner: CliRunner) -> None:
        result = runner.invoke(main, ["serve", "--no-schedule"])

        assert result.exit_code == 0, result.output
        assert "disabled" in result.output
