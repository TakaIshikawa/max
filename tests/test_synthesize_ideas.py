"""Tests for idea synthesis — intra-cluster, cross-cluster, CLI command."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from max.analysis.dedup import IdeaCluster
from max.analysis.synthesize_ideas import (
    ComplementaryGroup,
    CrossClusterDetectionOutput,
    CrossClusterSynthesisOutput,
    IntraClusterOutput,
    SynthesizedIdeaOutput,
    SynthesisResult,
    _ideas_to_json,
    _output_to_unit,
    run_synthesis,
)
from max.cli import main
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


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
    problem: str = "No standard way to test MCP servers",
    solution: str = "A CLI tool that validates MCP server implementations",
) -> BuildableUnit:
    return BuildableUnit(
        id=id,
        title=title,
        one_liner=f"One liner for {title}",
        category=category,
        ideation_mode=IdeationMode.DIRECT,
        problem=problem,
        solution=solution,
        target_users="both",
        value_proposition=f"Value prop for {title}",
        inspiring_insights=[f"ins-{id}"],
        evidence_signals=[f"sig-{id}"],
        tech_approach="TypeScript CLI",
        suggested_stack={"language": "typescript"},
        composability_notes="Integrates with CI/CD",
        status=status,
        domain=domain,
    )


def _make_dim(value: float = 7.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _make_eval(unit_id: str = "bu-test001", score: float = 75.0) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_make_dim(8.0),
        addressable_scale=_make_dim(7.0),
        build_effort=_make_dim(7.0),
        composability=_make_dim(8.0),
        competitive_density=_make_dim(6.0),
        timing_fit=_make_dim(7.0),
        compounding_value=_make_dim(7.0),
        overall_score=score,
        recommendation="yes",
    )


def _make_cluster(
    ideas: list[tuple[BuildableUnit, UtilityEvaluation | None]],
) -> IdeaCluster:
    """Build a cluster from a list of (unit, eval) pairs."""
    best_unit, best_ev = max(ideas, key=lambda x: x[1].overall_score if x[1] else 0.0)
    return IdeaCluster(
        representative=best_unit,
        representative_eval=best_ev,
        members=ideas,
        centroid=[0.5] * 10,
    )


def _mock_synthesized_output(title: str = "Synthesized Idea") -> SynthesizedIdeaOutput:
    return SynthesizedIdeaOutput(
        title=title,
        one_liner=f"A synthesized {title}",
        category="cli_tool",
        problem="Unified problem",
        solution="Combined solution",
        target_users="both",
        value_proposition="Stronger value prop",
        inspiring_insights=["ins-a", "ins-b"],
        tech_approach="Unified approach",
        suggested_stack={"language": "typescript"},
        composability_notes="Composes well",
        synthesis_rationale="Combined best of both",
    )


# ── Output Conversion ────────────────────────────────────────────


class TestOutputToUnit:
    def test_unions_insights_and_signals(self):
        idea_a = _make_unit(id="bu-a")
        idea_a.inspiring_insights = ["ins-1", "ins-2"]
        idea_a.evidence_signals = ["sig-1"]
        idea_b = _make_unit(id="bu-b")
        idea_b.inspiring_insights = ["ins-2", "ins-3"]
        idea_b.evidence_signals = ["sig-2"]

        output = _mock_synthesized_output()
        unit = _output_to_unit(output, source_ideas=[idea_a, idea_b], mode=IdeationMode.SYNTHESIS)

        assert set(unit.inspiring_insights) >= {"ins-1", "ins-2", "ins-3"}
        assert set(unit.evidence_signals) == {"sig-1", "sig-2"}
        assert unit.source_idea_ids == ["bu-a", "bu-b"]
        assert unit.ideation_mode == IdeationMode.SYNTHESIS

    def test_picks_most_common_domain(self):
        ideas = [
            _make_unit(id="bu-1", domain="devtools"),
            _make_unit(id="bu-2", domain="devtools"),
            _make_unit(id="bu-3", domain="aitools"),
        ]
        output = _mock_synthesized_output()
        unit = _output_to_unit(output, source_ideas=ideas, mode=IdeationMode.SYNTHESIS)
        assert unit.domain == "devtools"

    def test_validates_target_users(self):
        output = _mock_synthesized_output()
        output.target_users = "invalid_value"
        unit = _output_to_unit(output, source_ideas=[_make_unit()], mode=IdeationMode.SYNTHESIS)
        assert unit.target_users == "both"


# ── Ideas to JSON ────────────────────────────────────────────────


class TestIdeasToJson:
    def test_serializes_required_fields(self):
        unit = _make_unit()
        result = _ideas_to_json([unit])
        import json
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["id"] == "bu-test001"
        assert data[0]["title"] == "MCP Test Framework"
        assert "problem" in data[0]
        assert "solution" in data[0]


# ── Intra-Cluster Synthesis ──────────────────────────────────────


class TestSynthesizeCluster:
    @patch("max.analysis.synthesize_ideas.structured_call")
    def test_calls_llm_and_returns_unit(self, mock_call):
        mock_call.return_value = IntraClusterOutput(
            synthesized_idea=_mock_synthesized_output("Merged MCP Tool")
        )

        ideas = [
            (_make_unit(id="bu-1", title="Tool A"), _make_eval("bu-1", 75.0)),
            (_make_unit(id="bu-2", title="Tool B"), _make_eval("bu-2", 65.0)),
        ]
        cluster = _make_cluster(ideas)

        from max.analysis.synthesize_ideas import synthesize_cluster
        result = synthesize_cluster(cluster)

        assert result.title == "Merged MCP Tool"
        assert result.ideation_mode == IdeationMode.SYNTHESIS
        assert set(result.source_idea_ids) == {"bu-1", "bu-2"}
        mock_call.assert_called_once()
        assert mock_call.call_args.kwargs["stage"] == "synthesis_ideas"


# ── Cross-Cluster Detection ─────────────────────────────────────


class TestDetectComplementaryGroups:
    @patch("max.analysis.synthesize_ideas.structured_call")
    def test_returns_valid_groups(self, mock_call):
        mock_call.return_value = CrossClusterDetectionOutput(
            complementary_groups=[
                ComplementaryGroup(
                    idea_ids=["bu-1", "bu-2"],
                    complementarity_reason="Testing + monitoring",
                    combined_value_proposition="Full observability",
                    synergy_score=0.8,
                ),
                ComplementaryGroup(
                    idea_ids=["bu-3", "bu-99"],  # bu-99 doesn't exist
                    complementarity_reason="Invalid",
                    combined_value_proposition="Invalid",
                    synergy_score=0.7,
                ),
            ]
        )

        ideas = [_make_unit(id="bu-1"), _make_unit(id="bu-2"), _make_unit(id="bu-3")]

        from max.analysis.synthesize_ideas import detect_complementary_groups
        groups = detect_complementary_groups(ideas, max_groups=5)

        # Only the first group is valid (bu-99 doesn't exist in ideas)
        assert len(groups) == 1
        assert groups[0].idea_ids == ["bu-1", "bu-2"]

    @patch("max.analysis.synthesize_ideas.structured_call")
    def test_filters_low_synergy(self, mock_call):
        mock_call.return_value = CrossClusterDetectionOutput(
            complementary_groups=[
                ComplementaryGroup(
                    idea_ids=["bu-1", "bu-2"],
                    complementarity_reason="Weak",
                    combined_value_proposition="Meh",
                    synergy_score=0.4,  # Below 0.6 threshold
                ),
            ]
        )

        ideas = [_make_unit(id="bu-1"), _make_unit(id="bu-2")]

        from max.analysis.synthesize_ideas import detect_complementary_groups
        groups = detect_complementary_groups(ideas)
        assert len(groups) == 0

    def test_returns_empty_for_single_idea(self):
        from max.analysis.synthesize_ideas import detect_complementary_groups
        groups = detect_complementary_groups([_make_unit()])
        assert groups == []


# ── Cross-Cluster Synthesis ──────────────────────────────────────


class TestSynthesizeGroup:
    @patch("max.analysis.synthesize_ideas.structured_call")
    def test_calls_llm_with_cross_synthesis_mode(self, mock_call):
        mock_call.return_value = CrossClusterSynthesisOutput(
            synthesized_idea=_mock_synthesized_output("Cross Product")
        )

        ideas = [_make_unit(id="bu-1"), _make_unit(id="bu-2")]
        group = ComplementaryGroup(
            idea_ids=["bu-1", "bu-2"],
            complementarity_reason="Testing + Monitoring",
            combined_value_proposition="Full coverage",
            synergy_score=0.85,
        )

        from max.analysis.synthesize_ideas import synthesize_group
        result = synthesize_group(ideas, group)

        assert result.title == "Cross Product"
        assert result.ideation_mode == IdeationMode.CROSS_SYNTHESIS
        assert set(result.source_idea_ids) == {"bu-1", "bu-2"}


# ── Run Synthesis Orchestrator ───────────────────────────────────


class TestRunSynthesis:
    def test_dry_run_no_llm_calls(self):
        ideas = [
            (_make_unit(id="bu-1"), _make_eval("bu-1")),
            (_make_unit(id="bu-2"), _make_eval("bu-2")),
        ]
        cluster = _make_cluster(ideas)

        result = run_synthesis([cluster], dry_run=True)
        assert len(result.intra_synthesized) == 0
        assert len(result.source_idea_ids) == 2

    def test_skips_single_member_clusters(self):
        single_idea = [(_make_unit(id="bu-solo"), _make_eval("bu-solo"))]
        cluster = _make_cluster(single_idea)

        result = run_synthesis([cluster], dry_run=True)
        assert len(result.source_idea_ids) == 0

    @patch("max.analysis.synthesize_ideas.synthesize_cluster")
    def test_intra_cluster_synthesis(self, mock_synth):
        new_unit = _make_unit(id="bu-synth", title="Synthesized")
        new_unit.source_idea_ids = ["bu-1", "bu-2"]
        mock_synth.return_value = new_unit

        ideas = [
            (_make_unit(id="bu-1"), _make_eval("bu-1")),
            (_make_unit(id="bu-2"), _make_eval("bu-2")),
        ]
        cluster = _make_cluster(ideas)

        result = run_synthesis([cluster])
        assert len(result.intra_synthesized) == 1
        assert result.intra_synthesized[0].title == "Synthesized"

    @patch("max.analysis.synthesize_ideas.synthesize_group")
    @patch("max.analysis.synthesize_ideas.detect_complementary_groups")
    @patch("max.analysis.synthesize_ideas.synthesize_cluster")
    def test_cross_cluster_synthesis(self, mock_intra, mock_detect, mock_cross):
        # Set up intra synthesis (no multi-member clusters)
        mock_intra.return_value = _make_unit(id="bu-synth")

        # Set up cross detection
        mock_detect.return_value = [
            ComplementaryGroup(
                idea_ids=["bu-solo1", "bu-solo2"],
                complementarity_reason="Complementary",
                combined_value_proposition="Combined value",
                synergy_score=0.8,
            ),
        ]

        # Set up cross synthesis
        cross_unit = _make_unit(id="bu-cross", title="Cross Synthesized")
        cross_unit.source_idea_ids = ["bu-solo1", "bu-solo2"]
        mock_cross.return_value = cross_unit

        # Create clusters: 2 singletons
        cluster1 = _make_cluster([(_make_unit(id="bu-solo1"), _make_eval("bu-solo1"))])
        cluster2 = _make_cluster([(_make_unit(id="bu-solo2"), _make_eval("bu-solo2"))])

        result = run_synthesis([cluster1, cluster2], cross_cluster=True)
        assert len(result.cross_synthesized) == 1
        assert result.complementary_groups_found == 1


# ── CLI Command ──────────────────────────────────────────────────


class TestSynthesizeCommand:
    def test_no_ideas(self, runner):
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = []

        with patch("max.store.db.Store", return_value=mock_store):
            result = runner.invoke(main, ["synthesize"])
            assert result.exit_code == 0
            assert "No ideas to synthesize" in result.output

    def test_no_evaluated_ideas(self, runner):
        unit = _make_unit(status="draft")
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = [unit]
        mock_store.get_evaluation.return_value = None

        with patch("max.store.db.Store", return_value=mock_store):
            result = runner.invoke(main, ["synthesize"])
            assert result.exit_code == 0
            assert "No evaluated ideas" in result.output

    def test_skips_rejected_and_duplicate(self, runner):
        rejected = _make_unit(id="bu-rej", status="rejected")
        duplicate = _make_unit(id="bu-dup", status="duplicate")
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = [rejected, duplicate]

        with patch("max.store.db.Store", return_value=mock_store):
            result = runner.invoke(main, ["synthesize"])
            assert result.exit_code == 0
            assert "No ideas to synthesize" in result.output

    def test_dry_run(self, runner):
        units = [
            _make_unit(id="bu-1", title="Idea A"),
            _make_unit(id="bu-2", title="Idea B"),
        ]
        evals = {
            "bu-1": _make_eval("bu-1", 75.0),
            "bu-2": _make_eval("bu-2", 65.0),
        }
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = units
        mock_store.get_evaluation.side_effect = lambda uid: evals.get(uid)

        # Mock cluster_ideas to return a multi-member cluster
        with patch("max.store.db.Store", return_value=mock_store), \
             patch("max.analysis.dedup.cluster_ideas") as mock_cluster:
            cluster = _make_cluster([(units[0], evals["bu-1"]), (units[1], evals["bu-2"])])
            mock_cluster.return_value = [cluster]

            result = runner.invoke(main, ["synthesize", "--dry-run"])
            assert result.exit_code == 0
            assert "Dry run" in result.output

    def test_stores_synthesized_ideas(self, runner):
        units = [
            _make_unit(id="bu-1", title="Idea A"),
            _make_unit(id="bu-2", title="Idea B"),
        ]
        evals = {
            "bu-1": _make_eval("bu-1", 75.0),
            "bu-2": _make_eval("bu-2", 65.0),
        }
        mock_store = MagicMock()
        mock_store.get_buildable_units.return_value = units
        mock_store.get_evaluation.side_effect = lambda uid: evals.get(uid)
        mock_store.get_buildable_unit.side_effect = lambda uid: next(
            (u for u in units if u.id == uid), None
        )
        mock_store.insert_buildable_unit.side_effect = lambda u: u

        synth_result = SynthesisResult(
            intra_synthesized=[_make_unit(id="bu-synth", title="Merged")],
            source_idea_ids=["bu-1", "bu-2"],
        )
        synth_result.intra_synthesized[0].source_idea_ids = ["bu-1", "bu-2"]

        with patch("max.store.db.Store", return_value=mock_store), \
             patch("max.analysis.dedup.cluster_ideas") as mock_cluster, \
             patch("max.analysis.synthesize_ideas.run_synthesis", return_value=synth_result):
            cluster = _make_cluster([(units[0], evals["bu-1"]), (units[1], evals["bu-2"])])
            mock_cluster.return_value = [cluster]

            result = runner.invoke(main, ["synthesize"])
            assert result.exit_code == 0
            assert mock_store.insert_buildable_unit.called
            assert mock_store.insert_feedback.called
            assert mock_store.update_buildable_unit_status.called


# ── Robustness & Error Handling ──────────────────────────────────


class TestSynthesisExceptionHandling:
    @patch("max.analysis.synthesize_ideas.synthesize_cluster")
    def test_cluster_synthesis_exception_skipped_counter(self, mock_synth):
        """Test that cluster synthesis exceptions increment skipped counter."""
        mock_synth.side_effect = [
            Exception("LLM API failure"),
            _make_unit(id="bu-ok", title="OK"),
        ]

        ideas1 = [
            (_make_unit(id="bu-1"), _make_eval("bu-1")),
            (_make_unit(id="bu-2"), _make_eval("bu-2")),
        ]
        ideas2 = [
            (_make_unit(id="bu-3"), _make_eval("bu-3")),
            (_make_unit(id="bu-4"), _make_eval("bu-4")),
        ]

        cluster1 = _make_cluster(ideas1)
        cluster2 = _make_cluster(ideas2)

        result = run_synthesis([cluster1, cluster2])

        # First cluster failed, second succeeded
        assert result.skipped_clusters == 1
        assert len(result.intra_synthesized) == 1
        assert result.intra_synthesized[0].id == "bu-ok"

    @patch("max.analysis.synthesize_ideas.synthesize_cluster")
    def test_all_clusters_fail_returns_empty_result(self, mock_synth):
        """Test that all clusters failing returns empty result with correct skipped count."""
        mock_synth.side_effect = Exception("Total failure")

        ideas = [
            (_make_unit(id="bu-1"), _make_eval("bu-1")),
            (_make_unit(id="bu-2"), _make_eval("bu-2")),
        ]
        cluster = _make_cluster(ideas)

        result = run_synthesis([cluster])

        assert result.skipped_clusters == 1
        assert len(result.intra_synthesized) == 0
        assert len(result.source_idea_ids) == 0

    @patch("max.analysis.synthesize_ideas.detect_complementary_groups")
    def test_cross_cluster_detection_exception_continues(self, mock_detect):
        """Test that cross-cluster detection exception doesn't abandon phase."""
        mock_detect.side_effect = Exception("Detection failed")

        cluster1 = _make_cluster([(_make_unit(id="bu-1"), _make_eval("bu-1"))])
        cluster2 = _make_cluster([(_make_unit(id="bu-2"), _make_eval("bu-2"))])

        result = run_synthesis([cluster1, cluster2], cross_cluster=True)

        # Should continue with empty groups instead of crashing
        assert result.complementary_groups_found == 0
        assert len(result.cross_synthesized) == 0


class TestLLMOutputValidation:
    def test_invalid_inspiring_insights_type_defaults_to_empty(self):
        """Test that non-list inspiring_insights defaults to empty list."""
        # Explicitly type as Any to test runtime validation of invalid value
        invalid_insights: Any = "not-a-list"

        output = _mock_synthesized_output()
        output.inspiring_insights = invalid_insights

        unit = _output_to_unit(output, source_ideas=[_make_unit()], mode=IdeationMode.SYNTHESIS)

        # Should still have insights from source ideas, but not from invalid output
        assert isinstance(unit.inspiring_insights, list)

    def test_empty_target_users_defaults_with_warning(self):
        """Test that empty target_users defaults to 'both'."""
        output = _mock_synthesized_output()
        output.target_users = ""

        unit = _output_to_unit(output, source_ideas=[_make_unit()], mode=IdeationMode.SYNTHESIS)

        assert unit.target_users == "both"

    def test_invalid_target_users_defaults_with_warning(self):
        """Test that invalid target_users defaults to 'both' with warning."""
        output = _mock_synthesized_output()
        output.target_users = "invalid_value"

        unit = _output_to_unit(output, source_ideas=[_make_unit()], mode=IdeationMode.SYNTHESIS)

        assert unit.target_users == "both"

    def test_non_numeric_synergy_score_handled_gracefully(self):
        """Test that non-numeric synergy_score is handled gracefully."""
        from max.analysis.synthesize_ideas import detect_complementary_groups

        # Create a group manually with a non-numeric score bypassing Pydantic validation
        with patch("max.analysis.synthesize_ideas.structured_call") as mock_call:
            # Explicitly type as Any to test runtime validation of invalid value
            invalid_score: Any = "invalid"

            # Create a valid group first
            group = ComplementaryGroup(
                idea_ids=["bu-1", "bu-2"],
                complementarity_reason="Test",
                combined_value_proposition="Test value",
                synergy_score=0.8,
            )
            # Then set the score to an invalid value after creation
            group.synergy_score = invalid_score

            mock_call.return_value = CrossClusterDetectionOutput(
                complementary_groups=[group]
            )

            ideas = [_make_unit(id="bu-1"), _make_unit(id="bu-2")]
            groups = detect_complementary_groups(ideas)

            # Group should be filtered out due to 0.0 score (below 0.6 threshold)
            assert len(groups) == 0

    def test_synergy_score_clamping_logged(self):
        """Test that synergy_score clamping occurs and is logged."""
        from max.analysis.synthesize_ideas import detect_complementary_groups

        with patch("max.analysis.synthesize_ideas.structured_call") as mock_call:
            mock_call.return_value = CrossClusterDetectionOutput(
                complementary_groups=[
                    ComplementaryGroup(
                        idea_ids=["bu-1", "bu-2"],
                        complementarity_reason="Test",
                        combined_value_proposition="Test value",
                        synergy_score=1.5,  # Above 1.0, should be clamped
                    ),
                ]
            )

            ideas = [_make_unit(id="bu-1"), _make_unit(id="bu-2")]
            groups = detect_complementary_groups(ideas)

            # Should be clamped to 1.0 (still passes 0.6 threshold)
            assert len(groups) == 1
            assert groups[0].synergy_score == 1.0

    def test_invalid_idea_ids_filtered_from_groups(self):
        """Test that invalid idea IDs are filtered from complementary groups."""
        from max.analysis.synthesize_ideas import detect_complementary_groups

        with patch("max.analysis.synthesize_ideas.structured_call") as mock_call:
            mock_call.return_value = CrossClusterDetectionOutput(
                complementary_groups=[
                    ComplementaryGroup(
                        idea_ids=["bu-1", "bu-999", "bu-2", "bu-888"],  # bu-999, bu-888 don't exist
                        complementarity_reason="Test",
                        combined_value_proposition="Test value",
                        synergy_score=0.8,
                    ),
                ]
            )

            ideas = [_make_unit(id="bu-1"), _make_unit(id="bu-2")]
            groups = detect_complementary_groups(ideas)

            # Invalid IDs should be filtered, but group still has 2 valid IDs
            assert len(groups) == 1
            assert set(groups[0].idea_ids) == {"bu-1", "bu-2"}

    def test_group_with_too_few_valid_ids_filtered_out(self):
        """Test that groups with < 2 valid IDs after filtering are excluded."""
        from max.analysis.synthesize_ideas import detect_complementary_groups

        with patch("max.analysis.synthesize_ideas.structured_call") as mock_call:
            mock_call.return_value = CrossClusterDetectionOutput(
                complementary_groups=[
                    ComplementaryGroup(
                        idea_ids=["bu-1", "bu-999"],  # Only 1 valid ID
                        complementarity_reason="Test",
                        combined_value_proposition="Test value",
                        synergy_score=0.8,
                    ),
                ]
            )

            ideas = [_make_unit(id="bu-1"), _make_unit(id="bu-2")]
            groups = detect_complementary_groups(ideas)

            # Group should be filtered out (< 2 valid IDs)
            assert len(groups) == 0


# ── Store Integration ────────────────────────────────────────────


class TestStoreSynthesisFields:
    def test_source_idea_ids_stored_and_retrieved(self, tmp_path):
        from max.store.db import Store

        db_path = tmp_path / "test.db"
        with patch("max.store.db.DB_PATH", db_path):
            store = Store(db_path=db_path)
            try:
                unit = _make_unit(id="bu-synth")
                unit.source_idea_ids = ["bu-1", "bu-2", "bu-3"]
                unit.ideation_mode = IdeationMode.SYNTHESIS

                store.insert_buildable_unit(unit)
                retrieved = store.get_buildable_unit("bu-synth")

                assert retrieved is not None
                assert retrieved.source_idea_ids == ["bu-1", "bu-2", "bu-3"]
                assert retrieved.ideation_mode == IdeationMode.SYNTHESIS
            finally:
                store.close()

    def test_empty_source_idea_ids_by_default(self, tmp_path):
        from max.store.db import Store

        db_path = tmp_path / "test.db"
        with patch("max.store.db.DB_PATH", db_path):
            store = Store(db_path=db_path)
            try:
                unit = _make_unit(id="bu-normal")
                store.insert_buildable_unit(unit)
                retrieved = store.get_buildable_unit("bu-normal")

                assert retrieved is not None
                assert retrieved.source_idea_ids == []
            finally:
                store.close()
