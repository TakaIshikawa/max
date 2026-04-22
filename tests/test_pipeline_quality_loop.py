"""Pipeline wiring tests for the optional ideation quality loop."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from max.ideation.critique import IdeaCritique
from max.pipeline.dedup import DedupResult
from max.pipeline.runner import run_pipeline
from max.profiles.schema import DomainContext
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory


def _unit(unit_id: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title="Specific Clinic Workflow",
        one_liner="Automates one clinic workflow",
        category="workflow_automation",
        problem="Manual workflow",
        solution="Focused automation",
        value_proposition="Saves time",
        specific_user="clinic coordinator",
        buyer="clinic administrator",
        workflow_context="daily queue review",
        evidence_rationale="Backed by insight.",
        inspiring_insights=["ins-1"],
    )


def _evaluation(unit_id: str) -> UtilityEvaluation:
    score = DimensionScore(value=8, confidence=0.8, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=80,
        recommendation="yes",
        weights_used={},
    )


def test_run_pipeline_quality_loop_wires_critique_revision_and_gate():
    insight = Insight(
        id="ins-1",
        category=InsightCategory.GAP,
        title="Manual queue pain",
        summary="Manual queue review is painful.",
        evidence=[],
        confidence=0.8,
        domains=["healthcare"],
    )
    draft = _unit("bu-draft")
    revised = _unit("bu-revised")
    revised.title = "Revised Clinic Workflow"
    critique = IdeaCritique(
        title=draft.title,
        urgency=8,
        buyer_clarity=8,
        specificity=8,
        evidence_support=7,
        feasibility=7,
        differentiation=6,
        distribution_path=7,
        domain_risk=8,
        novelty=6,
        usefulness=8,
        reasoning="Strong workflow fit.",
    )

    store = MagicMock()
    store.insert_pipeline_run = MagicMock()
    store.update_pipeline_run = MagicMock()
    store.get_feedback_outcomes.return_value = []
    store.count_signals.side_effect = [0, 0]
    store.get_unsynthesized_signals.return_value = []
    store.get_insights.return_value = [insight]
    store.get_buildable_units.return_value = []
    store.get_signal.return_value = None
    store.get_insight.return_value = insight
    store.close = MagicMock()

    with (
        patch("max.pipeline.runner.Store", MagicMock(return_value=store)),
        patch("max.pipeline.runner.SemanticIndex", MagicMock()),
        patch("max.pipeline.runner.token_tracker", MagicMock(
            reset=MagicMock(),
            summary=MagicMock(return_value={}),
            estimated_cost_usd=MagicMock(return_value=0.0),
            cost_by_stage=MagicMock(return_value={}),
        )),
        patch("max.pipeline.runner.get_adapted_weights", return_value=({}, False)),
        patch("max.pipeline.runner._fetch_all_signals", return_value=([], {}, {})),
        patch("max.pipeline.runner.detect_gaps", return_value=[]),
        patch("max.pipeline.runner.format_gaps_for_ideation", return_value=None),
        patch("max.pipeline.runner.analyze_retrospective", return_value=None),
        patch("max.pipeline.runner.ideate", return_value=[draft]),
        patch("max.pipeline.runner.build_evidence_pack", return_value=MagicMock()),
        patch("max.pipeline.runner.critique_ideas", return_value=[critique]),
        patch("max.pipeline.runner.apply_critiques", side_effect=lambda units, critiques: units),
        patch("max.pipeline.runner.revise_ideas", return_value=[revised]),
        patch("max.pipeline.runner.quality_gate", return_value=([revised], [])),
        patch("max.pipeline.runner.dedup_buildable_units", return_value=DedupResult([revised], 0)),
        patch("max.pipeline.runner.evaluate", return_value=_evaluation("bu-revised")),
    ):
        result = run_pipeline(
            quality_loop_enabled=True,
            stages=["detect_gaps", "retrospective", "ideate", "evaluate"],
        )

    assert result.draft_ideas_generated == 1
    assert result.ideas_revised == 1
    assert result.ideas_rejected_by_quality_gate == 0
    assert result.ideas_generated == 1
    assert result.ideas_evaluated == 1
    store.insert_idea_memory.assert_called_once()
    assert store.insert_idea_memory.call_args.kwargs["outcome"] == "quality_passed"
    store.insert_idea_critique.assert_called_once()
    assert store.insert_idea_critique.call_args.args[0] == "bu-revised"


def test_dry_run_quality_loop_estimates_critique_and_revision_calls():
    insights = [
        Insight(
            id=f"ins-{i}",
            category=InsightCategory.GAP,
            title=f"Workflow pain {i}",
            summary="Developer workflow pain.",
            evidence=[],
            confidence=0.8,
            domains=["devtools"],
        )
        for i in range(12)
    ]
    store = MagicMock()
    store.get_unsynthesized_signals.return_value = []
    store.get_insights.return_value = insights
    store.get_feedback_outcomes.return_value = []
    store.close = MagicMock()

    with (
        patch("max.pipeline.runner.Store", MagicMock(return_value=store)),
        patch("max.pipeline.runner.get_all_adapters", return_value=[]),
        patch("max.pipeline.runner.token_tracker", MagicMock(reset=MagicMock())),
    ):
        result = run_pipeline(
            dry_run=True,
            quality_loop_enabled=True,
            draft_count=4,
            stages=["ideate", "evaluate"],
            profile=MagicMock(
                domain=DomainContext(
                    name="developer-tools",
                    description="Developer tools",
                    categories=["application"],
                    target_user_types=["humans"],
                ),
                sources=[],
                output_dir=".max-output",
                signal_limit=2,
                evaluation=MagicMock(min_score=50.0, weight_profile="default"),
                ideation_mode="direct",
                quality_loop_enabled=True,
                draft_count=4,
            ),
        )

    ideate_stage = next(s for s in result.stages if s.name == "ideate")
    evaluate_stage = next(s for s in result.stages if s.name == "evaluate")
    assert ideate_stage.would_process == 12
    assert ideate_stage.estimated_llm_calls == 3
    assert evaluate_stage.would_process <= 4


def test_quality_loop_persists_unit_quality_record_when_critique_mapping_missing():
    insight = Insight(
        id="ins-1",
        category=InsightCategory.GAP,
        title="Manual queue pain",
        summary="Manual queue review is painful.",
        evidence=[],
        confidence=0.8,
        domains=["healthcare"],
    )
    draft = _unit("bu-draft")
    revised = _unit("bu-revised")
    revised.title = "Renamed Revised Idea"
    revised.quality_score = 7.0
    revised.novelty_score = 6.0
    revised.usefulness_score = 8.0
    revised.rejection_tags = []

    store = MagicMock()
    store.insert_pipeline_run = MagicMock()
    store.update_pipeline_run = MagicMock()
    store.get_feedback_outcomes.return_value = []
    store.count_signals.side_effect = [0, 0]
    store.get_unsynthesized_signals.return_value = []
    store.get_insights.return_value = [insight]
    store.get_buildable_units.return_value = []
    store.get_signal.return_value = None
    store.get_insight.return_value = insight
    store.close = MagicMock()

    with (
        patch("max.pipeline.runner.Store", MagicMock(return_value=store)),
        patch("max.pipeline.runner.SemanticIndex", MagicMock()),
        patch("max.pipeline.runner.token_tracker", MagicMock(
            reset=MagicMock(),
            summary=MagicMock(return_value={}),
            estimated_cost_usd=MagicMock(return_value=0.0),
            cost_by_stage=MagicMock(return_value={}),
        )),
        patch("max.pipeline.runner.get_adapted_weights", return_value=({}, False)),
        patch("max.pipeline.runner.ideate", return_value=[draft]),
        patch("max.pipeline.runner.build_evidence_pack", return_value=MagicMock(to_json=MagicMock(return_value="{}"))),
        patch("max.pipeline.runner.critique_ideas", return_value=[]),
        patch("max.pipeline.runner.apply_critiques", side_effect=lambda units, critiques: units),
        patch("max.pipeline.runner.revise_ideas", return_value=[revised]),
        patch("max.pipeline.runner.quality_gate", return_value=([revised], [])),
        patch("max.pipeline.runner.dedup_buildable_units", return_value=DedupResult([revised], 0)),
        patch("max.pipeline.runner.evaluate", return_value=_evaluation("bu-revised")),
    ):
        run_pipeline(
            quality_loop_enabled=True,
            stages=["ideate", "evaluate"],
        )

    store.insert_idea_critique.assert_called_once()
    _, critique = store.insert_idea_critique.call_args.args
    assert critique["quality_score"] == 7.0
    assert critique["novelty"] == 6.0
    assert critique["usefulness"] == 8.0
