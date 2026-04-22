"""Tests for the CLI interface (max.cli).

All CLI commands use lazy (in-function) imports, so patches target the
source modules (e.g. ``max.store.db.Store``) rather than ``max.cli.Store``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from max.cli import main
from max.publisher.webhook import WebhookPublishError
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


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


def _mock_store(**overrides) -> MagicMock:
    """Build a mock Store with sensible defaults. Override individual methods via kwargs."""
    store = MagicMock()
    store.get_buildable_units.return_value = overrides.get("units", [])
    store.get_buildable_unit.return_value = overrides.get("unit", None)
    store.get_evaluation.return_value = overrides.get("evaluation", None)
    store.get_latest_feedback.return_value = overrides.get("latest_feedback", None)
    store.get_idea_critiques.return_value = overrides.get("idea_critiques", [])
    store.get_feedback_outcomes.return_value = overrides.get("feedback_outcomes", [])
    store.get_signals.return_value = overrides.get("signals", [])
    store.get_design_brief.return_value = overrides.get("design_brief", None)
    store.get_design_briefs.return_value = overrides.get("design_briefs", [])
    store.get_domain_quality_scores.return_value = overrides.get("domain_quality_scores", [])
    store.get_domain_quality_memory.return_value = overrides.get("domain_quality_memory", [])
    store.insert_domain_quality_eval_run.return_value = overrides.get("eval_run_id", "dqeval-test001")
    store.insert_domain_quality_eval_item.return_value = overrides.get("eval_item_id", "dqitem-test001")
    store.close.return_value = None
    return store


def _design_brief_dict(brief_id: str = "dbf-test001") -> dict:
    return {
        "id": brief_id,
        "title": "AgentAdversarialBench",
        "domain": "developer-tools",
        "theme": "agent-security-evaluation",
        "readiness_score": 86.0,
        "lead_idea_id": "bu-test001",
        "buyer": "engineering manager",
        "specific_user": "platform engineer",
        "workflow_context": "CI gate before deployment",
        "why_this_now": "Agent tool use is growing.",
        "merged_product_concept": "Run adversarial workflow fixtures.",
        "synthesis_rationale": "Strong lead idea.",
        "mvp_scope": ["CLI runner"],
        "first_milestones": ["Prototype CLI"],
        "validation_plan": "Run with three teams.",
        "risks": ["Framework churn"],
        "source_idea_ids": ["bu-test001"],
        "design_status": "candidate",
        "created_at": "2026-04-22T00:00:00+00:00",
        "updated_at": "2026-04-22T00:00:00+00:00",
        "sources": [{"idea_id": "bu-test001", "role": "lead", "rank": 0}],
    }


class TestRestoreCommand:
    @patch("max.store.db.Store")
    def test_restore_dry_run_groups_summary_and_respects_limit(
        self, MockStore: MagicMock, runner: CliRunner
    ) -> None:
        store = MagicMock()
        store.get_archived_signal_ids.return_value = ["sig-1"]
        store.get_archived_insight_ids.return_value = ["ins-1"]
        store.get_archived_idea_ids.return_value = []
        store.close.return_value = None
        MockStore.return_value = store

        result = runner.invoke(main, ["restore", "--dry-run", "--limit", "2"])

        assert result.exit_code == 0, result.output
        assert "DRY RUN: No changes applied." in result.output
        assert "Would restore 2 archived record(s):" in result.output
        assert "signals:" in result.output
        assert "insights:" in result.output
        assert "ideas:" in result.output
        store.get_archived_signal_ids.assert_called_once()
        store.get_archived_insight_ids.assert_called_once()
        store.get_archived_idea_ids.assert_not_called()
        store.restore_signal.assert_not_called()

    @patch("max.store.db.Store")
    def test_restore_specific_archived_idea(
        self, MockStore: MagicMock, runner: CliRunner
    ) -> None:
        store = MagicMock()
        store.get_archived_idea_ids.return_value = ["bu-1"]
        store.restore_archived_idea.return_value = True
        store.close.return_value = None
        MockStore.return_value = store

        result = runner.invoke(
            main,
            ["restore", "--entity", "idea", "--id", "bu-1", "--before", "2026-04-22"],
        )

        assert result.exit_code == 0, result.output
        assert "Restored 1 archived record(s):" in result.output
        store.get_archived_idea_ids.assert_called_once()
        _, kwargs = store.get_archived_idea_ids.call_args
        assert kwargs["ids"] == ["bu-1"]
        assert kwargs["limit"] == 100
        store.restore_archived_idea.assert_called_once_with("bu-1")


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
        assert "Token usage:" in result.output
        assert "Top ideas:" in result.output
        assert "Cool Idea" in result.output


# ── profiles command ────────────────────────────────────────────────


class TestProfilesCommand:
    """Tests for ``max profiles`` commands."""

    @patch("max.profiles.loader.validate_profile_files")
    def test_profiles_validate_all_success(self, mock_validate, runner: CliRunner) -> None:
        from max.profiles.loader import ProfileFileValidationResult

        mock_validate.return_value = [
            ProfileFileValidationResult("devtools", Path("profiles/devtools.yaml"), []),
            ProfileFileValidationResult("healthcare", Path("profiles/healthcare.yaml"), []),
        ]

        result = runner.invoke(main, ["profiles", "validate"])

        assert result.exit_code == 0, result.output
        assert "devtools: OK" in result.output
        assert "healthcare: OK" in result.output
        mock_validate.assert_called_once_with(profile=None)

    @patch("max.profiles.loader.validate_profile_files")
    def test_profiles_validate_single_profile(self, mock_validate, runner: CliRunner) -> None:
        from max.profiles.loader import ProfileFileValidationResult

        mock_validate.return_value = [
            ProfileFileValidationResult("devtools", Path("profiles/devtools.yaml"), []),
        ]

        result = runner.invoke(main, ["profiles", "validate", "--profile", "devtools"])

        assert result.exit_code == 0, result.output
        assert result.output.strip() == "devtools: OK"
        mock_validate.assert_called_once_with(profile="devtools")

    @patch("max.profiles.loader.validate_profile_files")
    def test_profiles_validate_error_exits_nonzero(self, mock_validate, runner: CliRunner) -> None:
        from max.profiles.loader import ProfileFileValidationResult

        mock_validate.return_value = [
            ProfileFileValidationResult(
                "bad",
                Path("profiles/bad.yaml"),
                ["schema: sources.0.adapter: 'bogus' is not one of ['reddit']"],
            ),
        ]

        result = runner.invoke(main, ["profiles", "validate"])

        assert result.exit_code == 1
        assert "bad: ERROR" in result.output
        assert "schema: sources.0.adapter" in result.output

    @patch("max.profiles.loader.validate_profile_files")
    def test_profiles_validate_missing_profile(self, mock_validate, runner: CliRunner) -> None:
        mock_validate.side_effect = FileNotFoundError("Profile 'missing' not found")

        result = runner.invoke(main, ["profiles", "validate", "--profile", "missing"])

        assert result.exit_code != 0
        assert "Profile 'missing' not found" in result.output


class TestSourcesCommand:
    @patch("max.sources.registry.list_adapter_metadata")
    def test_sources_list_table(self, mock_metadata, runner: CliRunner) -> None:
        from max.sources.registry import AdapterMetadata

        mock_metadata.return_value = [
            AdapterMetadata(
                name="rss_feed",
                config_keys=["feeds", "tags", "max_age_days"],
                required_keys=["feeds"],
                description="Fetches RSS or Atom entries.",
            )
        ]

        result = runner.invoke(main, ["sources", "list"])

        assert result.exit_code == 0, result.output
        assert "Available source adapters:" in result.output
        assert "rss_feed" in result.output
        assert "Config keys: feeds, tags, max_age_days" in result.output
        assert "Required:    feeds" in result.output

    @patch("max.sources.registry.list_adapter_metadata")
    def test_sources_list_json(self, mock_metadata, runner: CliRunner) -> None:
        from max.sources.registry import AdapterMetadata

        mock_metadata.return_value = [
            AdapterMetadata(
                name="hackernews",
                config_keys=["filter_keywords"],
                required_keys=[],
                description="Fetches Hacker News stories.",
            )
        ]

        result = runner.invoke(main, ["sources", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload == [
            {
                "name": "hackernews",
                "config_keys": ["filter_keywords"],
                "required_keys": [],
                "description": "Fetches Hacker News stories.",
            }
        ]


class TestBlueprintExportCommands:
    @patch("max.store.db.Store")
    def test_export_design_brief_stdout_json(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(unit=_make_unit())
        store.get_design_brief.return_value = _design_brief_dict()
        MockStore.return_value = store

        result = runner.invoke(main, ["export-design-brief", "dbf-test001"])

        assert result.exit_code == 0, result.output
        assert '"schema_version": "max.blueprint.source_brief.v1"' in result.output
        assert '"entity_type": "design_brief"' in result.output
        assert '"source_ideas"' in result.output
        store.get_design_brief.assert_called_once_with("dbf-test001")

    @patch("max.store.db.Store")
    def test_export_design_brief_writes_yaml(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(unit=_make_unit())
        store.get_design_brief.return_value = _design_brief_dict()
        MockStore.return_value = store

        with runner.isolated_filesystem():
            result = runner.invoke(
                main,
                [
                    "export-design-brief",
                    "dbf-test001",
                    "--format",
                    "yaml",
                    "--output",
                    "brief.yaml",
                ],
            )
            assert result.exit_code == 0, result.output
            assert Path("brief.yaml").exists()
            assert "schema_version: max.blueprint.source_brief.v1" in Path("brief.yaml").read_text()

    @patch("max.store.db.Store")
    def test_export_design_briefs_batch(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(unit=_make_unit())
        store.get_design_briefs.return_value = [
            _design_brief_dict("dbf-one"),
            _design_brief_dict("dbf-two"),
        ]
        MockStore.return_value = store

        with runner.isolated_filesystem():
            result = runner.invoke(
                main,
                ["export-design-briefs", "--output", "out", "--format", "json"],
            )
            assert result.exit_code == 0, result.output
            assert Path("out/dbf-one.json").exists()
            assert Path("out/dbf-two.json").exists()
            assert "Wrote 2 Blueprint source brief(s)" in result.output

    @patch("max.store.db.Store")
    def test_export_design_brief_not_found(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store()
        store.get_design_brief.return_value = None
        MockStore.return_value = store

        result = runner.invoke(main, ["export-design-brief", "dbf-missing"])

        assert result.exit_code != 0
        assert "Design brief not found: dbf-missing" in result.output


class TestSpecPreviewCommand:
    @patch("max.store.db.Store")
    def test_spec_preview_stdout_json(self, MockStore: MagicMock, runner: CliRunner) -> None:
        store = _mock_store(unit=_make_unit(), evaluation=_make_evaluation())
        MockStore.return_value = store

        result = runner.invoke(main, ["spec-preview", "bu-test001", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["kind"] == "tact.project_spec"
        assert payload["source"]["idea_id"] == "bu-test001"
        assert payload["evaluation"]["overall_score"] == 78.0
        store.get_buildable_unit.assert_called_once_with("bu-test001")
        store.get_evaluation.assert_called_once_with("bu-test001")

    @patch("max.store.db.Store")
    def test_spec_preview_stdout_yaml(self, MockStore: MagicMock, runner: CliRunner) -> None:
        store = _mock_store(unit=_make_unit(), evaluation=_make_evaluation())
        MockStore.return_value = store

        result = runner.invoke(main, ["spec-preview", "bu-test001", "--format", "yaml"])

        assert result.exit_code == 0, result.output
        payload = yaml.safe_load(result.output)
        assert payload["schema_version"] == "tact-spec-preview/v1"
        assert payload["source"]["idea_id"] == "bu-test001"
        assert payload["project"]["title"] == "MCP Test Framework"

    @patch("max.store.db.Store")
    def test_spec_preview_writes_file(self, MockStore: MagicMock, runner: CliRunner) -> None:
        store = _mock_store(unit=_make_unit(), evaluation=_make_evaluation())
        MockStore.return_value = store

        with runner.isolated_filesystem():
            result = runner.invoke(
                main,
                ["spec-preview", "bu-test001", "--output", "out/spec.json"],
            )

            assert result.exit_code == 0, result.output
            assert result.output == ""
            payload = json.loads(Path("out/spec.json").read_text(encoding="utf-8"))
            assert payload["source"]["idea_id"] == "bu-test001"
            assert payload["evaluation"]["recommendation"] == "yes"

    @patch("max.store.db.Store")
    def test_spec_preview_missing_idea(self, MockStore: MagicMock, runner: CliRunner) -> None:
        store = _mock_store(unit=None)
        MockStore.return_value = store

        result = runner.invoke(main, ["spec-preview", "bu-missing"])

        assert result.exit_code != 0
        assert "Idea not found: bu-missing" in result.output
        store.get_evaluation.assert_not_called()


class TestPublishCommand:
    @patch("max.publisher.webhook.WebhookPublisher")
    @patch("max.store.db.Store")
    def test_publish_tact_spec_posts_generated_spec(
        self,
        MockStore: MagicMock,
        MockPublisher: MagicMock,
        runner: CliRunner,
    ) -> None:
        store = _mock_store(unit=_make_unit(), evaluation=_make_evaluation())
        MockStore.return_value = store
        publisher = MockPublisher.return_value
        publisher.publish.return_value.status_code = 202
        publisher.publish.return_value.attempts = 1
        publisher.publish.return_value.url = "https://example.com/hook"

        result = runner.invoke(
            main,
            [
                "publish",
                "bu-test001",
                "--webhook-url",
                "https://example.com/hook?token=secret",
                "--payload",
                "tact-spec",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = publisher.publish.call_args.args[0]
        assert payload["kind"] == "tact.project_spec"
        assert payload["source"]["idea_id"] == "bu-test001"
        publisher.publish.assert_called_once()
        assert publisher.publish.call_args.kwargs["payload_type"] == "tact-spec"
        MockPublisher.assert_called_once_with(
            "https://example.com/hook?token=secret",
            timeout=10.0,
            retries=2,
        )
        assert "Published tact-spec for bu-test001" in result.output
        assert "token=secret" not in result.output
        store.insert_publication_attempt.assert_called_once_with(
            idea_id="bu-test001",
            target_type="webhook",
            target_url="https://example.com/hook",
            status="success",
            response_status=202,
        )

    @patch("max.publisher.webhook.WebhookPublisher")
    @patch("max.store.db.Store")
    def test_publish_blueprint_posts_generated_source_brief(
        self,
        MockStore: MagicMock,
        MockPublisher: MagicMock,
        runner: CliRunner,
    ) -> None:
        store = _mock_store(unit=_make_unit())
        store.get_design_brief.return_value = _design_brief_dict()
        MockStore.return_value = store
        publisher = MockPublisher.return_value
        publisher.publish.return_value.status_code = 200
        publisher.publish.return_value.attempts = 1
        publisher.publish.return_value.url = "https://example.com/hook"

        result = runner.invoke(
            main,
            [
                "publish",
                "dbf-test001",
                "--webhook-url",
                "https://example.com/hook",
                "--payload",
                "blueprint",
                "--timeout",
                "2.5",
                "--retries",
                "4",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = publisher.publish.call_args.args[0]
        assert payload["schema_version"] == "max.blueprint.source_brief.v1"
        assert payload["source"]["id"] == "dbf-test001"
        assert publisher.publish.call_args.kwargs["payload_type"] == "blueprint"
        MockPublisher.assert_called_once_with(
            "https://example.com/hook",
            timeout=2.5,
            retries=4,
        )
        assert "Published blueprint for dbf-test001" in result.output
        store.insert_publication_attempt.assert_called_once_with(
            idea_id="bu-test001",
            target_type="webhook",
            target_url="https://example.com/hook",
            status="success",
            response_status=200,
        )

    @patch("max.publisher.webhook.WebhookPublisher")
    @patch("max.store.db.Store")
    def test_publish_records_webhook_failure(
        self,
        MockStore: MagicMock,
        MockPublisher: MagicMock,
        runner: CliRunner,
    ) -> None:
        store = _mock_store(unit=_make_unit(), evaluation=_make_evaluation())
        MockStore.return_value = store
        publisher = MockPublisher.return_value
        publisher.redacted_url = "https://example.com/hook"
        publisher.publish.side_effect = WebhookPublishError("webhook returned HTTP 500")

        result = runner.invoke(
            main,
            [
                "publish",
                "bu-test001",
                "--webhook-url",
                "https://example.com/hook",
                "--payload",
                "tact-spec",
            ],
        )

        assert result.exit_code != 0
        assert "webhook returned HTTP 500" in result.output
        store.insert_publication_attempt.assert_called_once_with(
            idea_id="bu-test001",
            target_type="webhook",
            target_url="https://example.com/hook",
            status="failure",
            error="webhook returned HTTP 500",
        )

    @patch("max.store.db.Store")
    def test_publish_missing_tact_spec_idea(self, MockStore: MagicMock, runner: CliRunner) -> None:
        store = _mock_store(unit=None)
        MockStore.return_value = store

        result = runner.invoke(
            main,
            ["publish", "bu-missing", "--webhook-url", "https://example.com/hook"],
        )

        assert result.exit_code != 0
        assert "Idea not found: bu-missing" in result.output


class TestDomainQualityCommands:
    @patch("max.store.db.Store")
    def test_domain_quality_score(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(
            unit=_make_unit(),
            domain_quality_scores=[
                {
                    "id": "dqs-1",
                    "buildable_unit_id": "bu-test001",
                    "domain": "developer-tools",
                    "profile_name": "devtools",
                    "rubric_version": "v1",
                    "dimensions": {"buyer_clarity": 8.0},
                    "overall_score": 78.0,
                    "passed_gate": True,
                    "rejection_tags": [],
                    "reasoning": "Good domain fit.",
                    "created_at": "2026-04-22T00:00:00+00:00",
                }
            ],
        )
        MockStore.return_value = store

        result = runner.invoke(main, ["domain-quality", "score", "bu-test001"])

        assert result.exit_code == 0, result.output
        assert "78.0" in result.output
        assert "[passed]" in result.output
        assert "Good domain fit." in result.output

    @patch("max.store.db.Store")
    def test_domain_quality_memory(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(
            domain_quality_memory=[
                {
                    "id": "dqm-1",
                    "domain": "healthcare",
                    "outcome": "rejected",
                    "pattern": "AI doctor: diagnosis without review",
                    "source_idea_id": "bu-1",
                    "source_design_brief_id": None,
                    "tags": ["autonomous_diagnosis"],
                    "score": 30.0,
                    "notes": "unsafe",
                    "created_at": "2026-04-22T00:00:00+00:00",
                }
            ],
        )
        MockStore.return_value = store

        result = runner.invoke(main, ["domain-quality", "memory", "--domain", "healthcare"])

        assert result.exit_code == 0, result.output
        assert "AI doctor" in result.output
        assert "autonomous_diagnosis" in result.output

    @patch("max.pipeline.runner.run_pipeline")
    @patch("max.profiles.loader.load_profile")
    @patch("max.store.db.Store")
    def test_domain_quality_eval_runs_baseline_and_rubric(
        self,
        MockStore,
        mock_load_profile,
        mock_run_pipeline,
        runner: CliRunner,
    ) -> None:
        from max.pipeline.runner import PipelineResult
        from max.profiles.schema import (
            DomainContext,
            DomainQualityConfig,
            DomainQualityDimension,
            EvaluationConfig,
            PipelineProfile,
        )

        profile = PipelineProfile(
            name="devtools",
            domain=DomainContext(
                name="developer-tools",
                description="Developer tools",
                categories=["cli_tool"],
                target_user_types=["developers"],
            ),
            domain_quality=DomainQualityConfig(
                enabled=True,
                rubric_version="v1",
                scoring_dimensions={
                    "buyer_clarity": DomainQualityDimension(weight=1.0),
                },
            ),
            evaluation=EvaluationConfig(min_score=50.0),
            quality_loop_enabled=True,
            draft_count=8,
        )
        mock_load_profile.return_value = profile

        baseline_unit = _make_unit(id="bu-baseline", title="Baseline Idea")
        baseline_unit.domain = "developer-tools"
        rubric_unit = _make_unit(id="bu-rubric", title="Rubric Idea")
        rubric_unit.domain = "developer-tools"

        store = _mock_store(evaluation=_make_evaluation(score=82.0))
        store.get_buildable_units.side_effect = [
            [],
            [baseline_unit],
            [baseline_unit, rubric_unit],
        ]
        store.get_domain_quality_scores.side_effect = [
            [],
            [
                {
                    "overall_score": 74.0,
                    "passed_gate": True,
                }
            ],
        ]
        MockStore.return_value = store

        mock_run_pipeline.side_effect = [
            PipelineResult(
                run_id="run-baseline",
                draft_ideas_generated=4,
                ideas_evaluated=1,
                avg_idea_score=70.0,
            ),
            PipelineResult(
                run_id="run-rubric",
                draft_ideas_generated=4,
                ideas_evaluated=1,
                avg_idea_score=82.0,
                avg_domain_quality_score=74.0,
                ideas_rejected_by_domain_quality=1,
            ),
        ]

        result = runner.invoke(
            main,
            [
                "domain-quality",
                "eval",
                "--profile",
                "devtools",
                "--draft-count",
                "4",
                "--stages",
                "ideate,evaluate",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Domain quality eval: dqeval-test001" in result.output
        assert "baseline" in result.output
        assert "rubric" in result.output
        assert mock_run_pipeline.call_count == 2
        assert mock_run_pipeline.call_args_list[0].kwargs["profile"].domain_quality.enabled is False
        assert mock_run_pipeline.call_args_list[1].kwargs["profile"].domain_quality.enabled is True
        store.insert_domain_quality_eval_run.assert_called_once()
        assert store.insert_domain_quality_eval_item.call_count == 2
        first_item = store.insert_domain_quality_eval_item.call_args_list[0].kwargs
        second_item = store.insert_domain_quality_eval_item.call_args_list[1].kwargs
        assert first_item["buildable_unit_id"] == "bu-baseline"
        assert first_item["cohort"] == "baseline"
        assert first_item["domain_quality_score"] is None
        assert second_item["buildable_unit_id"] == "bu-rubric"
        assert second_item["cohort"] == "rubric"
        assert second_item["domain_quality_score"] == 74.0


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

    @patch("max.store.db.Store")
    def test_ideas_json_format(self, MockStore, runner: CliRunner) -> None:
        unit = _make_unit(id="bu-001", title="Idea Alpha", status="evaluated")
        unit.domain = "devtools"
        unit.quality_score = 7.5
        unit.novelty_score = 7.0
        unit.usefulness_score = 8.0
        unit.rejection_tags = ["too_broad"]
        evaluation = _make_evaluation("bu-001", score=78.0)
        store = _mock_store(
            units=[unit],
            latest_feedback={
                "outcome": "approved",
                "reason": "strong candidate",
                "created_at": "2026-04-22T00:00:00+00:00",
            },
        )
        store.get_evaluation.return_value = evaluation
        MockStore.return_value = store

        result = runner.invoke(main, ["ideas", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload == [
            {
                "id": "bu-001",
                "title": "Idea Alpha",
                "one_liner": "Standardized testing for MCP servers",
                "category": "cli_tool",
                "domain": "devtools",
                "status": "evaluated",
                "review_state": "approved",
                "feedback_outcome": "approved",
                "feedback_reason": "strong candidate",
                "reviewed_at": "2026-04-22T00:00:00+00:00",
                "graph_labels": ["Idea", "ReviewApproved"],
                "is_approved": True,
                "quality_score": 7.5,
                "novelty_score": 7.0,
                "usefulness_score": 8.0,
                "rejection_tags": ["too_broad"],
                "score": 78.0,
                "recommendation": "yes",
            }
        ]

    @patch("max.store.db.Store")
    def test_ideas_output_writes_json(self, MockStore, runner: CliRunner, tmp_path: Path) -> None:
        unit = _make_unit(id="bu-001", title="Idea Alpha")
        store = _mock_store(units=[unit])
        store.get_evaluation.return_value = None
        MockStore.return_value = store
        output_path = tmp_path / "ideas.json"

        result = runner.invoke(main, ["ideas", "--output", str(output_path)])

        assert result.exit_code == 0, result.output
        assert result.output == f"Wrote 1 idea(s) to {output_path}\n"
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload[0]["id"] == "bu-001"
        assert payload[0]["score"] is None
        assert payload[0]["recommendation"] is None


class TestExportIdeasCommand:
    """Tests for ``max export ideas``."""

    @patch("max.store.db.Store")
    def test_export_ideas_jsonl_stdout(self, MockStore, runner: CliRunner) -> None:
        unit = _make_unit(id="bu-001", title="Idea Alpha", status="evaluated")
        unit.domain = "devtools"
        unit.quality_score = 7.5
        unit.novelty_score = 7.0
        unit.usefulness_score = 8.0
        unit.rejection_tags = ["too_broad"]
        evaluation = _make_evaluation("bu-001", score=78.0)
        store = _mock_store(
            units=[unit],
            latest_feedback={
                "outcome": "approved",
                "reason": "strong candidate",
                "approval_score": 9,
                "created_at": "2026-04-22T00:00:00+00:00",
            },
        )
        store.get_evaluation.return_value = evaluation
        MockStore.return_value = store

        result = runner.invoke(main, ["export", "ideas", "--format", "jsonl"])

        assert result.exit_code == 0, result.output
        rows = [json.loads(line) for line in result.output.splitlines()]
        assert rows == [
            {
                "id": "bu-001",
                "title": "Idea Alpha",
                "one_liner": "Standardized testing for MCP servers",
                "category": "cli_tool",
                "domain": "devtools",
                "status": "evaluated",
                "evaluation_score": 78.0,
                "recommendation": "yes",
                "latest_feedback_outcome": "approved",
                "latest_feedback_reason": "strong candidate",
                "latest_feedback_score": 9,
                "latest_feedback_at": "2026-04-22T00:00:00+00:00",
                "quality_score": 7.5,
                "novelty_score": 7.0,
                "usefulness_score": 8.0,
                "rejection_tags": ["too_broad"],
                "inspiring_insight_ids": ["ins-test001"],
                "evidence_signal_ids": ["sig-test001"],
                "source_idea_ids": [],
                "created_at": unit.created_at.isoformat(),
                "updated_at": unit.updated_at.isoformat(),
            }
        ]
        store.get_buildable_units.assert_called_once_with(limit=100, status=None, domain=None)
        store.close.assert_called_once()

    @patch("max.store.db.Store")
    def test_export_ideas_filters_and_writes_csv(
        self,
        MockStore,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        strong = _make_unit(id="bu-strong", title="Strong Idea", status="evaluated")
        weak = _make_unit(id="bu-weak", title="Weak Idea", status="evaluated")
        store = _mock_store(units=[strong, weak])
        store.get_evaluation.side_effect = lambda uid: {
            "bu-strong": _make_evaluation("bu-strong", score=82.0),
            "bu-weak": _make_evaluation("bu-weak", score=49.0),
        }[uid]
        store.get_latest_feedback.return_value = None
        MockStore.return_value = store
        output_path = tmp_path / "ideas.csv"

        result = runner.invoke(
            main,
            [
                "export",
                "ideas",
                "--format",
                "csv",
                "--status",
                "evaluated",
                "--domain",
                "devtools",
                "--min-score",
                "75",
                "--limit",
                "5",
                "--output",
                str(output_path),
            ],
        )

        assert result.exit_code == 0, result.output
        assert result.output == f"Wrote 1 idea(s) to {output_path}\n"
        csv_text = output_path.read_text(encoding="utf-8")
        assert "evaluation_score,recommendation" in csv_text
        assert "bu-strong" in csv_text
        assert "bu-weak" not in csv_text
        store.get_buildable_units.assert_called_once_with(
            limit=5,
            status="evaluated",
            domain="devtools",
        )

    def test_idea_export_helpers_render_jsonl_and_csv(self) -> None:
        from max.analysis.export import idea_export_record, render_idea_export

        unit = _make_unit(id="bu-001")
        record = idea_export_record(
            unit,
            _make_evaluation("bu-001", score=88.0),
            {"outcome": "approved", "reason": "ship it", "approval_score": 10, "created_at": "now"},
        )

        jsonl = render_idea_export([record], fmt="jsonl")
        assert json.loads(jsonl)["evaluation_score"] == 88.0
        assert json.loads(jsonl)["evidence_signal_ids"] == ["sig-test001"]

        csv_text = render_idea_export([record], fmt="csv")
        assert csv_text.splitlines()[0].startswith("id,title,one_liner")
        assert "\"[\"\"sig-test001\"\"]\"" in csv_text


# ── import-signals command ─────────────────────────────────────────


class TestImportSignalsCommand:
    """Tests for ``max import-signals``."""

    @patch("max.store.db.Store")
    def test_import_signals_jsonl_counts_created_duplicate_invalid(
        self,
        MockStore,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        input_path = tmp_path / "signals.jsonl"
        input_path.write_text(
            "\n".join(
                [
                    json.dumps({
                        "title": "New signal",
                        "content": "Useful evidence",
                        "url": "https://example.com/new",
                    }),
                    json.dumps({
                        "title": "Duplicate signal",
                        "content": "Already known",
                        "url": "https://example.com/dup",
                    }),
                    json.dumps({"title": "Missing content", "url": "https://example.com/bad"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        duplicate = Signal(
            id="sig-existing",
            source_type=SignalSourceType.FORUM,
            source_adapter="manual",
            title="Existing",
            content="Existing",
            url="https://example.com/dup",
        )
        store = _mock_store()
        store.get_signal_by_url.side_effect = (
            lambda url: duplicate if url == "https://example.com/dup" else None
        )

        def insert_signal(signal: Signal) -> Signal:
            signal.id = signal.id or "sig-created"
            return signal

        store.insert_signal.side_effect = insert_signal
        store.get_signal.return_value = Signal(
            id="sig-created",
            source_type=SignalSourceType.ARTICLE,
            source_adapter="manual",
            title="New signal",
            content="Useful evidence",
            url="https://example.com/new",
        )
        MockStore.return_value = store

        result = runner.invoke(
            main,
            [
                "import-signals",
                str(input_path),
                "--source-adapter",
                "manual",
                "--source-type",
                "article",
                "--tag",
                "imported",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "created:   1" in result.output
        assert "duplicate: 1" in result.output
        assert "invalid:   1" in result.output
        assert "failed:    0" in result.output
        store.insert_signal.assert_called_once()
        imported = store.insert_signal.call_args.args[0]
        assert imported.source_adapter == "manual"
        assert imported.source_type == SignalSourceType.ARTICLE
        assert imported.tags == ["imported"]
        store.close.assert_called_once()

    @patch("max.store.db.Store")
    def test_import_signals_dry_run_does_not_insert(
        self,
        MockStore,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        input_path = tmp_path / "signals.csv"
        input_path.write_text(
            "title,content,url,tags\nCSV Signal,Body,https://example.com/csv,\"csv,manual\"\n",
            encoding="utf-8",
        )
        store = _mock_store()
        store.get_signal_by_url.return_value = None
        MockStore.return_value = store

        result = runner.invoke(
            main,
            ["import-signals", str(input_path), "--dry-run", "--tag", "imported"],
        )

        assert result.exit_code == 0, result.output
        assert "created:   1" in result.output
        assert "Dry run: no changes applied." in result.output
        store.insert_signal.assert_not_called()
        store.close.assert_called_once()


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


# ── feedback command ───────────────────────────────────────────────


class TestFeedbackCommand:
    """Tests for ``max feedback``."""

    @patch("max.store.db.Store")
    def test_feedback_not_found(self, MockStore, runner: CliRunner) -> None:
        MockStore.return_value = _mock_store(unit=None)
        result = runner.invoke(main, ["feedback", "bu-missing", "approved"])
        assert result.exit_code == 0
        assert "Not found: bu-missing" in result.output

    @pytest.mark.parametrize("outcome", ["approved", "rejected", "abandoned"])
    @patch("max.store.db.Store")
    def test_feedback_valid_outcomes(self, MockStore, outcome: str, runner: CliRunner) -> None:
        unit = _make_unit()
        store = _mock_store(unit=unit)
        MockStore.return_value = store

        result = runner.invoke(main, ["feedback", "bu-test001", outcome])

        assert result.exit_code == 0
        store.insert_feedback.assert_called_once_with("bu-test001", outcome, "")
        store.update_buildable_unit_status.assert_called_once_with("bu-test001", outcome)
        assert "Recorded: MCP Test Framework" in result.output
        store.close.assert_called_once()

    @patch("max.store.db.Store")
    def test_feedback_with_reason(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(unit=_make_unit())
        MockStore.return_value = store

        result = runner.invoke(main, ["feedback", "bu-test001", "rejected", "-r", "Too niche"])

        assert result.exit_code == 0
        store.insert_feedback.assert_called_once_with("bu-test001", "rejected", "Too niche")

    @patch("max.store.db.Store")
    def test_feedback_with_score(self, MockStore, runner: CliRunner) -> None:
        store = _mock_store(unit=_make_unit())
        MockStore.return_value = store

        result = runner.invoke(main, ["feedback", "bu-test001", "approved", "-s", "8"])

        assert result.exit_code == 0
        store.insert_feedback.assert_called_once_with("bu-test001", "approved", "", approval_score=8)
        assert "(8/10)" in result.output

    @patch("max.store.db.Store")
    def test_feedback_score_rejected_error(self, MockStore, runner: CliRunner) -> None:
        result = runner.invoke(main, ["feedback", "bu-test001", "rejected", "-s", "5"])
        assert "only valid for 'approved'" in result.output

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


# ── focus command group ────────────────────────────────────────────


@pytest.fixture
def isolated_focus(tmp_path, monkeypatch):
    """Redirect focus config to a tmp location."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    monkeypatch.setattr("max.focus.get_profiles_dir", lambda: profiles_dir)
    return tmp_path / ".max" / "focus.yaml"


def _mock_profile(name: str, domain_name: str):
    from max.profiles.schema import DomainContext, PipelineProfile

    return PipelineProfile(
        name=name,
        domain=DomainContext(
            name=domain_name,
            description=f"{domain_name} domain",
            categories=["cli_tool"],
            target_user_types=["developers"],
        ),
    )


class TestFocusCommand:
    """Tests for ``max focus`` group."""

    @patch("max.profiles.loader.list_profiles")
    @patch("max.profiles.loader.load_profile")
    def test_list_when_no_config(
        self, mock_load, mock_list, runner: CliRunner, isolated_focus,
    ) -> None:
        mock_list.return_value = ["devtools", "healthcare"]
        mock_load.side_effect = lambda n: _mock_profile(n, {"devtools": "developer-tools", "healthcare": "healthcare"}[n])

        result = runner.invoke(main, ["focus", "list"])

        assert result.exit_code == 0, result.output
        assert "not configured" in result.output
        assert "developer-tools" in result.output
        assert "healthcare" in result.output

    @patch("max.profiles.loader.list_profiles")
    @patch("max.profiles.loader.load_profile")
    def test_set_valid_domains(
        self, mock_load, mock_list, runner: CliRunner, isolated_focus,
    ) -> None:
        mock_list.return_value = ["devtools", "healthcare"]
        mock_load.side_effect = lambda n: _mock_profile(n, {"devtools": "developer-tools", "healthcare": "healthcare"}[n])

        result = runner.invoke(main, ["focus", "set", "developer-tools", "healthcare"])

        assert result.exit_code == 0, result.output
        assert "Focus set to" in result.output

        from max.focus import load_focus_domains
        assert load_focus_domains() == ["developer-tools", "healthcare"]

    @patch("max.profiles.loader.list_profiles")
    @patch("max.profiles.loader.load_profile")
    def test_set_rejects_unknown_domain(
        self, mock_load, mock_list, runner: CliRunner, isolated_focus,
    ) -> None:
        mock_list.return_value = ["devtools"]
        mock_load.side_effect = lambda n: _mock_profile(n, "developer-tools")

        result = runner.invoke(main, ["focus", "set", "bogus-domain"])

        assert result.exit_code != 0
        assert "Unknown domain" in result.output
        from max.focus import load_focus_domains
        assert load_focus_domains() is None  # unchanged

    @patch("max.profiles.loader.list_profiles")
    @patch("max.profiles.loader.load_profile")
    def test_add_domain(
        self, mock_load, mock_list, runner: CliRunner, isolated_focus,
    ) -> None:
        from max.focus import save_focus_domains

        mock_list.return_value = ["devtools", "healthcare"]
        mock_load.side_effect = lambda n: _mock_profile(n, {"devtools": "developer-tools", "healthcare": "healthcare"}[n])
        save_focus_domains(["developer-tools"])

        result = runner.invoke(main, ["focus", "add", "healthcare"])

        assert result.exit_code == 0, result.output
        from max.focus import load_focus_domains
        assert load_focus_domains() == ["developer-tools", "healthcare"]

    @patch("max.profiles.loader.list_profiles")
    @patch("max.profiles.loader.load_profile")
    def test_remove_domain(
        self, mock_load, mock_list, runner: CliRunner, isolated_focus,
    ) -> None:
        from max.focus import save_focus_domains

        mock_list.return_value = ["devtools", "healthcare"]
        mock_load.side_effect = lambda n: _mock_profile(n, {"devtools": "developer-tools", "healthcare": "healthcare"}[n])
        save_focus_domains(["developer-tools", "healthcare"])

        result = runner.invoke(main, ["focus", "remove", "healthcare"])

        assert result.exit_code == 0, result.output
        from max.focus import load_focus_domains
        assert load_focus_domains() == ["developer-tools"]

    def test_remove_last_clears_filter(
        self, runner: CliRunner, isolated_focus,
    ) -> None:
        from max.focus import save_focus_domains

        save_focus_domains(["developer-tools"])

        result = runner.invoke(main, ["focus", "remove", "developer-tools"])

        assert result.exit_code == 0, result.output
        from max.focus import load_focus_domains
        assert load_focus_domains() is None

    def test_clear(self, runner: CliRunner, isolated_focus) -> None:
        from max.focus import save_focus_domains

        save_focus_domains(["developer-tools"])

        result = runner.invoke(main, ["focus", "clear"])

        assert result.exit_code == 0, result.output
        from max.focus import load_focus_domains
        assert load_focus_domains() is None

    def test_clear_when_already_clear(
        self, runner: CliRunner, isolated_focus,
    ) -> None:
        result = runner.invoke(main, ["focus", "clear"])

        assert result.exit_code == 0, result.output
        assert "already cleared" in result.output


# ── run --profile all focus filter ─────────────────────────────────


class TestRunAllWithFocus:
    """Tests for ``max run --profile all`` focus filtering."""

    @patch("max.pipeline.runner.run_post_pipeline")
    @patch("max.pipeline.runner.run_pipeline")
    @patch("max.profiles.loader.load_profile")
    @patch("max.profiles.loader.list_profiles")
    @patch("max.config.MAX_PROFILE", "")
    def test_filters_out_of_focus_profiles(
        self,
        mock_list,
        mock_load,
        mock_run_pipeline,
        mock_post,
        runner: CliRunner,
        isolated_focus,
    ) -> None:
        from max.focus import save_focus_domains
        from max.pipeline.runner import PipelineResult, PostPipelineResult

        profiles = {
            "devtools": "developer-tools",
            "healthcare": "healthcare",
            "legaltech": "legaltech",
            "fintech": "fintech",
        }
        mock_list.return_value = list(profiles.keys())
        mock_load.side_effect = lambda n: _mock_profile(n, profiles[n])
        mock_run_pipeline.return_value = PipelineResult(
            avg_insight_confidence=0.8, avg_idea_score=70.0, top_ideas=[],
        )
        mock_post.return_value = PostPipelineResult()
        save_focus_domains(["developer-tools", "healthcare"])

        result = runner.invoke(main, ["run", "--profile", "all"])

        assert result.exit_code == 0, result.output
        assert "Skipping 2 out-of-focus profile(s)" in result.output
        assert "legaltech" in result.output
        assert "fintech" in result.output
        # Only devtools + healthcare pipelines should run
        assert mock_run_pipeline.call_count == 2

    @patch("max.pipeline.runner.run_post_pipeline")
    @patch("max.pipeline.runner.run_pipeline")
    @patch("max.profiles.loader.load_profile")
    @patch("max.profiles.loader.list_profiles")
    @patch("max.config.MAX_PROFILE", "")
    def test_include_all_bypasses_focus(
        self,
        mock_list,
        mock_load,
        mock_run_pipeline,
        mock_post,
        runner: CliRunner,
        isolated_focus,
    ) -> None:
        from max.focus import save_focus_domains
        from max.pipeline.runner import PipelineResult, PostPipelineResult

        profiles = {
            "devtools": "developer-tools",
            "legaltech": "legaltech",
            "fintech": "fintech",
        }
        mock_list.return_value = list(profiles.keys())
        mock_load.side_effect = lambda n: _mock_profile(n, profiles[n])
        mock_run_pipeline.return_value = PipelineResult(
            avg_insight_confidence=0.8, avg_idea_score=70.0, top_ideas=[],
        )
        mock_post.return_value = PostPipelineResult()
        save_focus_domains(["developer-tools"])

        result = runner.invoke(main, ["run", "--profile", "all", "--include-all"])

        assert result.exit_code == 0, result.output
        assert "Skipping" not in result.output
        assert mock_run_pipeline.call_count == 3

    @patch("max.pipeline.runner.run_post_pipeline")
    @patch("max.pipeline.runner.run_pipeline")
    @patch("max.profiles.loader.load_profile")
    @patch("max.profiles.loader.list_profiles")
    @patch("max.config.MAX_PROFILE", "")
    def test_no_focus_runs_all_as_before(
        self,
        mock_list,
        mock_load,
        mock_run_pipeline,
        mock_post,
        runner: CliRunner,
        isolated_focus,
    ) -> None:
        from max.pipeline.runner import PipelineResult, PostPipelineResult

        profiles = {
            "devtools": "developer-tools",
            "legaltech": "legaltech",
        }
        mock_list.return_value = list(profiles.keys())
        mock_load.side_effect = lambda n: _mock_profile(n, profiles[n])
        mock_run_pipeline.return_value = PipelineResult(
            avg_insight_confidence=0.8, avg_idea_score=70.0, top_ideas=[],
        )
        mock_post.return_value = PostPipelineResult()

        result = runner.invoke(main, ["run", "--profile", "all"])

        assert result.exit_code == 0, result.output
        assert "Skipping" not in result.output
        assert mock_run_pipeline.call_count == 2
