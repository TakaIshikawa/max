"""CLI tests for quality-loop controls and inspection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from max.cli import main
from max.types.buildable_unit import BuildableUnit


def test_run_quality_loop_flags_override_profile():
    from max.pipeline.runner import PipelineResult
    from max.profiles.schema import DomainContext, PipelineProfile

    runner = CliRunner()
    profile = PipelineProfile(
        name="devtools",
        domain=DomainContext(
            name="developer-tools",
            description="Developer tools",
            categories=["application"],
            target_user_types=["humans"],
        ),
    )

    with (
        patch("max.profiles.loader.get_default_profile", return_value=profile),
        patch("max.pipeline.runner.run_pipeline", return_value=PipelineResult(
            draft_ideas_generated=4,
            ideas_revised=3,
            ideas_rejected_by_quality_gate=1,
            avg_novelty_score=6.5,
            avg_usefulness_score=8.0,
        )),
        patch("max.pipeline.runner.run_post_pipeline", return_value=MagicMock(
            duplicates_marked=0,
            ideas_synthesized=0,
            prior_art_checked=0,
            triage_auto_approved=0,
            triage_auto_rejected=0,
            triage_pending_review=0,
        )),
        patch("max.config.MAX_PROFILE", ""),
    ):
        result = runner.invoke(main, ["run", "--quality-loop", "--draft-count", "12"])

    assert result.exit_code == 0, result.output
    assert profile.quality_loop_enabled is True
    assert profile.draft_count == 12
    assert "Quality loop: on" in result.output
    assert "4 drafts, 3 revised, 1 rejected" in result.output


def test_ideas_show_critique():
    runner = CliRunner()
    unit = BuildableUnit(
        id="bu-cli-quality",
        title="CLI Quality Idea",
        one_liner="Show critique",
        category="application",
        problem="Critique is hidden",
        solution="Display it",
        value_proposition="Better review",
        quality_score=7.0,
    )
    store = MagicMock()
    store.get_buildable_units.return_value = [unit]
    store.get_evaluation.return_value = None
    store.get_idea_critiques.return_value = [{
        "dimensions": {"quality_score": 7.0, "novelty": 6.0, "usefulness": 8.0},
        "rejection_tags": ["needs_validation"],
    }]

    with patch("max.store.db.Store", return_value=store):
        result = runner.invoke(main, ["ideas", "--show-critique"])

    assert result.exit_code == 0, result.output
    assert "critique q=7.0" in result.output
    assert "needs_validation" in result.output


def test_inspect_evidence_pack():
    runner = CliRunner()
    unit = BuildableUnit(
        id="bu-cli-inspect",
        title="Inspect Idea",
        one_liner="Inspect evidence",
        category="application",
        problem="Evidence hidden",
        solution="Show pack",
        value_proposition="Better review",
        specific_user="reviewer",
        buyer="team lead",
        workflow_context="idea review",
    )
    store = MagicMock()
    store.get_buildable_unit.return_value = unit
    store.get_evaluation.return_value = None
    store.get_idea_critiques.return_value = [{
        "dimensions": {"quality_score": 7.0, "novelty": 6.0, "usefulness": 8.0},
        "rejection_tags": [],
        "reasoning": "Specific enough.",
        "evidence_pack": {"domain_name": "developer-tools"},
    }]

    with patch("max.store.db.Store", return_value=store):
        result = runner.invoke(main, ["inspect", "bu-cli-inspect", "--evidence-pack"])

    assert result.exit_code == 0, result.output
    assert "Latest Critique" in result.output
    assert "Evidence Pack" in result.output
    assert "developer-tools" in result.output
