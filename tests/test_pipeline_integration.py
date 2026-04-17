"""Integration tests for the pipeline runner with mocked source adapters.

Exercises run_pipeline end-to-end with controlled mock adapters, verifying
signal flow through all stages, dry-run mode, selective stage execution,
partial adapter failure, and zero-signal edge cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.analysis.triangulation import SignalCluster
from max.pipeline.dedup import DedupResult
from max.pipeline.runner import PipelineResult, run_pipeline
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.pipeline import DryRunReport
from max.types.signal import Signal, SignalSourceType

# ── Helpers ──────────────────────────────────────────────────────────

_R = "max.pipeline.runner"


def _make_signal(id: str, adapter: str = "mock_source_a", **kw) -> Signal:
    defaults = dict(
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"Signal {id}",
        content=f"Content for signal {id}",
        url=f"https://example.com/{id}",
        credibility=0.7,
    )
    defaults.update(kw)
    return Signal(id=id, **defaults)


def _make_insight(id: str, evidence: list[str] | None = None, confidence: float = 0.8) -> Insight:
    return Insight(
        id=id,
        category=InsightCategory.GAP,
        title=f"Insight {id}",
        summary=f"Summary for {id}",
        evidence=evidence or [],
        confidence=confidence,
        domains=["test"],
        implications=["implication"],
        time_horizon="near_term",
    )


def _make_unit(id: str, insights: list[str] | None = None) -> BuildableUnit:
    return BuildableUnit(
        id=id,
        title=f"Unit {id}",
        one_liner=f"One-liner for {id}",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem=f"Problem {id}",
        solution=f"Solution {id}",
        value_proposition=f"Value {id}",
        inspiring_insights=insights or [],
        evidence_signals=[],
    )


def _dim(value: float) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _make_evaluation(unit_id: str, score: float) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_dim(8.0),
        addressable_scale=_dim(7.0),
        build_effort=_dim(7.5),
        composability=_dim(8.5),
        competitive_density=_dim(9.0),
        timing_fit=_dim(8.0),
        compounding_value=_dim(7.0),
        overall_score=score,
        strengths=["strong"],
        weaknesses=["weak"],
        recommendation="yes" if score >= 60 else "no",
        weights_used={"pain_severity": 0.2},
    )


def _make_cluster(topic: str, signals: list[Signal]) -> SignalCluster:
    roles: dict[str, int] = {}
    for s in signals:
        role = s.signal_role or "unknown"
        roles[role] = roles.get(role, 0) + 1
    return SignalCluster(
        topic=topic,
        signals=signals,
        source_diversity=0.5,
        avg_credibility=0.7,
        roles=roles,
        centroid=[],
    )


def _make_mock_store() -> MagicMock:
    """Build a mock Store with all methods the runner calls."""
    store = MagicMock()
    store.insert_pipeline_run = MagicMock()
    store.update_pipeline_run = MagicMock()
    store.insert_pipeline_run_domain = MagicMock()
    store.get_feedback_outcomes = MagicMock(return_value=[])
    store.count_signals = MagicMock(side_effect=[0, 0])
    store.insert_signal = MagicMock()
    store.get_unsynthesized_signals = MagicMock(return_value=[])
    store.mark_signals_synthesized = MagicMock()
    store.get_insights = MagicMock(return_value=[])
    store.insert_insight = MagicMock()
    store.get_buildable_units = MagicMock(return_value=[])
    store.insert_buildable_unit = MagicMock()
    store.update_buildable_unit_status = MagicMock()
    store.insert_evaluation = MagicMock()
    store.close = MagicMock()
    store.get_signal = MagicMock(return_value=None)
    store.get_insight = MagicMock(return_value=None)
    return store


def _base_patches(mock_store: MagicMock) -> dict[str, MagicMock | object]:
    """Return patch target -> mock for all external deps in the runner."""
    return {
        f"{_R}.Store": MagicMock(return_value=mock_store),
        f"{_R}.SemanticIndex": MagicMock(),
        f"{_R}.token_tracker": MagicMock(
            reset=MagicMock(),
            summary=MagicMock(return_value={"input": 100, "output": 200}),
            estimated_cost_usd=MagicMock(return_value=0.01),
            cost_by_stage=MagicMock(return_value={}),
        ),
        f"{_R}.get_adapted_weights": MagicMock(return_value=({"pain_severity": 0.2}, False)),
        f"{_R}.annotate_signals": MagicMock(),
        f"{_R}.triangulate": MagicMock(return_value=[]),
        f"{_R}.format_cluster_context": MagicMock(return_value=None),
        f"{_R}.detect_gaps": MagicMock(return_value=[]),
        f"{_R}.format_gaps_for_ideation": MagicMock(return_value=None),
        f"{_R}.analyze_retrospective": MagicMock(return_value=None),
        f"{_R}.format_retrospective_for_ideation": MagicMock(return_value=None),
        f"{_R}.synthesize": MagicMock(return_value=[]),
        f"{_R}.ideate": MagicMock(return_value=[]),
        f"{_R}.ideate_refinement": MagicMock(return_value=[]),
        f"{_R}.ideate_cross_domain": MagicMock(return_value=[]),
        f"{_R}.evaluate": MagicMock(),
        f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=[], duplicates=0)),
        f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=[], duplicates=0)),
        f"{_R}._fetch_all_signals": MagicMock(return_value=([], {}, {})),
    }


class _PatchCtx:
    """Convenience wrapper: apply all base patches, expose mocks by short name."""

    def __init__(self, overrides: dict | None = None):
        self.mock_store = _make_mock_store()
        self.patches_map = _base_patches(self.mock_store)
        if overrides:
            self.patches_map.update(overrides)
        self._patchers: list = []
        self.mocks: dict[str, MagicMock] = {}

    def __enter__(self) -> _PatchCtx:
        for target, mock_val in self.patches_map.items():
            p = patch(target, mock_val)
            self._patchers.append(p)
            started = p.start()
            short = target.rsplit(".", 1)[-1]
            self.mocks[short] = started
        return self

    def __exit__(self, *args):
        for p in self._patchers:
            p.stop()


# ═══════════════════════════════════════════════════════════════════════
# 1. Full pipeline run with multiple mocked sources
# ═══════════════════════════════════════════════════════════════════════


class TestFullPipelineWithMockedSources:
    """Exercise a complete pipeline run with 2-3 mocked sources returning synthetic signals."""

    def test_full_pipeline_flow_with_multiple_sources(self):
        """Signals from 3 adapters flow through all stages and produce evaluated ideas."""
        signals_a = [_make_signal("sa1", adapter="mock_source_a"), _make_signal("sa2", adapter="mock_source_a")]
        signals_b = [_make_signal("sb1", adapter="mock_source_b")]
        signals_c = [_make_signal("sc1", adapter="mock_source_c"), _make_signal("sc2", adapter="mock_source_c")]
        all_signals = signals_a + signals_b + signals_c

        insights = [_make_insight("i1", evidence=["sa1", "sb1"]), _make_insight("i2", evidence=["sc1"])]
        units = [_make_unit("u1", insights=["i1"]), _make_unit("u2", insights=["i2"])]
        evals = [_make_evaluation("u1", score=85.0), _make_evaluation("u2", score=72.0)]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 5])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=all_signals)

        eval_iter = iter(evals)
        fetch_alloc = {"mock_source_a": 2, "mock_source_b": 1, "mock_source_c": 2}
        adapter_metrics = {
            "mock_source_a": {"status": "ok", "signal_count": 2, "error_message": None, "duration_ms": 50},
            "mock_source_b": {"status": "ok", "signal_count": 1, "error_message": None, "duration_ms": 30},
            "mock_source_c": {"status": "ok", "signal_count": 2, "error_message": None, "duration_ms": 40},
        }

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(all_signals, fetch_alloc, adapter_metrics)),
            f"{_R}.synthesize": MagicMock(return_value=insights),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=units, duplicates=0)),
            f"{_R}.ideate": MagicMock(return_value=units),
            f"{_R}.evaluate": MagicMock(side_effect=lambda unit, **kw: next(eval_iter)),
        }

        with _PatchCtx(overrides) as ctx:
            result = run_pipeline(signal_limit=10, min_score=50.0)

        assert isinstance(result, PipelineResult)
        assert result.signals_fetched == 5
        assert result.signals_new == 5
        assert result.insights_generated == 2
        assert result.ideas_generated == 2
        assert result.ideas_evaluated == 2
        assert result.fetch_allocation == fetch_alloc
        assert result.adapter_metrics == adapter_metrics
        assert len(result.top_ideas) == 2
        # Top ideas sorted by score descending
        assert result.top_ideas[0]["score"] >= result.top_ideas[1]["score"]

    def test_signals_flow_through_all_stages(self):
        """Verify each stage is called in sequence: fetch → annotate → triangulate → synthesize → ideate → evaluate."""
        call_order = []

        signals = [_make_signal("s1"), _make_signal("s2")]
        insights = [_make_insight("i1")]
        units = [_make_unit("u1")]
        evaluation = _make_evaluation("u1", score=75.0)

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 2])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=signals)

        def track(name, return_value=None):
            def side_effect(*args, **kwargs):
                call_order.append(name)
                return return_value
            return side_effect

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(side_effect=track("fetch", (signals, {}, {}))),
            f"{_R}.annotate_signals": MagicMock(side_effect=track("annotate")),
            f"{_R}.triangulate": MagicMock(side_effect=track("triangulate", [])),
            f"{_R}.format_cluster_context": MagicMock(return_value=None),
            f"{_R}.synthesize": MagicMock(side_effect=track("synthesize", insights)),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
            f"{_R}.detect_gaps": MagicMock(side_effect=track("detect_gaps", [])),
            f"{_R}.format_gaps_for_ideation": MagicMock(return_value=None),
            f"{_R}.analyze_retrospective": MagicMock(side_effect=track("retrospective", None)),
            f"{_R}.format_retrospective_for_ideation": MagicMock(return_value=None),
            f"{_R}.ideate": MagicMock(side_effect=track("ideate", units)),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=units, duplicates=0)),
            f"{_R}.evaluate": MagicMock(side_effect=track("evaluate", evaluation)),
        }

        with _PatchCtx(overrides):
            result = run_pipeline(signal_limit=10, min_score=50.0)

        assert call_order == [
            "fetch",
            "annotate",
            "triangulate",
            "synthesize",
            "detect_gaps",
            "retrospective",
            "ideate",
            "evaluate",
        ]
        assert result.signals_fetched == 2
        assert result.insights_generated == 1
        assert result.ideas_generated == 1
        assert result.ideas_evaluated == 1

    def test_dedup_filters_duplicates(self):
        """When dedup removes items, the result reflects fewer insights/ideas."""
        signals = [_make_signal("s1")]
        all_insights = [_make_insight("i1"), _make_insight("i2"), _make_insight("i3")]
        kept_insights = [_make_insight("i1"), _make_insight("i3")]
        all_units = [_make_unit("u1"), _make_unit("u2")]
        kept_units = [_make_unit("u1")]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 1])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=signals)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {}, {})),
            f"{_R}.synthesize": MagicMock(return_value=all_insights),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=kept_insights, duplicates=1)),
            f"{_R}.ideate": MagicMock(return_value=all_units),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=kept_units, duplicates=1)),
            f"{_R}.evaluate": MagicMock(return_value=_make_evaluation("u1", score=80.0)),
        }

        with _PatchCtx(overrides):
            result = run_pipeline(signal_limit=5, min_score=50.0)

        assert result.insights_generated == 2  # 3 - 1 dup
        assert result.insights_duplicates_skipped == 1
        assert result.ideas_generated == 1  # 2 - 1 dup
        assert result.ideas_duplicates_skipped == 1


# ═══════════════════════════════════════════════════════════════════════
# 2. Dry-run mode
# ═══════════════════════════════════════════════════════════════════════


class TestDryRunMode:
    """Test dry-run produces expected output without side effects."""

    def test_dry_run_returns_report(self):
        """dry_run=True returns a DryRunReport, not PipelineResult."""
        mock_store = _make_mock_store()
        mock_store.get_unsynthesized_signals = MagicMock(return_value=[])
        mock_store.get_insights = MagicMock(return_value=[])
        mock_store.get_feedback_outcomes = MagicMock(return_value=[])

        with patch(f"{_R}.Store", return_value=mock_store), \
             patch(f"{_R}.get_all_adapters", return_value=[]), \
             patch(f"{_R}.token_tracker") as mock_tracker:
            mock_tracker.reset = MagicMock()
            result = run_pipeline(dry_run=True)

        assert isinstance(result, DryRunReport)
        assert isinstance(result.stages, list)
        assert len(result.stages) == len(["fetch", "annotate", "synthesize", "detect_gaps", "retrospective", "ideate", "evaluate"])
        assert isinstance(result.estimated_total_llm_calls, int)
        assert isinstance(result.estimated_token_budget, int)

    def test_dry_run_no_llm_calls(self):
        """dry_run mode should NOT call any LLM-dependent engines."""
        mock_store = _make_mock_store()
        mock_store.get_unsynthesized_signals = MagicMock(return_value=[])
        mock_store.get_insights = MagicMock(return_value=[])
        mock_store.get_feedback_outcomes = MagicMock(return_value=[])

        mock_synthesize = MagicMock()
        mock_ideate = MagicMock()
        mock_evaluate = MagicMock()

        with patch(f"{_R}.Store", return_value=mock_store), \
             patch(f"{_R}.get_all_adapters", return_value=[]), \
             patch(f"{_R}.synthesize", mock_synthesize), \
             patch(f"{_R}.ideate", mock_ideate), \
             patch(f"{_R}.evaluate", mock_evaluate), \
             patch(f"{_R}.token_tracker") as mock_tracker:
            mock_tracker.reset = MagicMock()
            result = run_pipeline(dry_run=True)

        mock_synthesize.assert_not_called()
        mock_ideate.assert_not_called()
        mock_evaluate.assert_not_called()

    def test_dry_run_no_data_written_to_store(self):
        """dry_run mode should not insert signals, insights, or ideas into the store."""
        mock_store = _make_mock_store()
        mock_store.get_unsynthesized_signals = MagicMock(return_value=[])
        mock_store.get_insights = MagicMock(return_value=[])
        mock_store.get_feedback_outcomes = MagicMock(return_value=[])

        with patch(f"{_R}.Store", return_value=mock_store), \
             patch(f"{_R}.get_all_adapters", return_value=[]), \
             patch(f"{_R}.token_tracker") as mock_tracker:
            mock_tracker.reset = MagicMock()
            run_pipeline(dry_run=True)

        mock_store.insert_signal.assert_not_called()
        mock_store.insert_insight.assert_not_called()
        mock_store.insert_buildable_unit.assert_not_called()
        mock_store.insert_evaluation.assert_not_called()
        mock_store.insert_pipeline_run.assert_not_called()

    def test_dry_run_stage_summaries_populated(self):
        """Each stage summary has meaningful fields."""
        mock_store = _make_mock_store()
        mock_store.get_unsynthesized_signals = MagicMock(return_value=[_make_signal("s1")])
        mock_store.get_insights = MagicMock(return_value=[_make_insight("i1")])
        mock_store.get_feedback_outcomes = MagicMock(return_value=[])

        mock_adapter = MagicMock()
        mock_adapter.name = "test_adapter"

        with patch(f"{_R}.Store", return_value=mock_store), \
             patch(f"{_R}.get_all_adapters", return_value=[mock_adapter]), \
             patch("max.pipeline.fetch_strategy.compute_fetch_allocation", return_value={"test_adapter": 10}), \
             patch(f"{_R}.token_tracker") as mock_tracker:
            mock_tracker.reset = MagicMock()
            result = run_pipeline(dry_run=True, signal_limit=10)

        assert isinstance(result, DryRunReport)
        stage_names = [s.name for s in result.stages]
        assert "fetch" in stage_names
        assert "synthesize" in stage_names
        assert "ideate" in stage_names
        assert "evaluate" in stage_names

        fetch_stage = next(s for s in result.stages if s.name == "fetch")
        assert fetch_stage.would_process == 10
        assert fetch_stage.skipped is False


# ═══════════════════════════════════════════════════════════════════════
# 3. Selective stage execution
# ═══════════════════════════════════════════════════════════════════════


class TestSelectiveStageExecution:
    """Test pipeline behavior when specific stages are selected."""

    def test_fetch_only(self):
        """Running only 'fetch' stage skips synthesis, ideation, and evaluation."""
        signals = [_make_signal("s1"), _make_signal("s2")]
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 2])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {"mock": 2}, {})),
        }

        with _PatchCtx(overrides) as ctx:
            result = run_pipeline(stages=["fetch"])

        assert result.signals_fetched == 2
        assert result.insights_generated == 0
        assert result.ideas_generated == 0
        assert result.ideas_evaluated == 0
        ctx.mocks["synthesize"].assert_not_called()
        ctx.mocks["ideate"].assert_not_called()
        ctx.mocks["evaluate"].assert_not_called()

    def test_fetch_and_synthesize_only(self):
        """Running 'fetch' + 'synthesize' stages skips ideation and evaluation."""
        signals = [_make_signal("s1")]
        insights = [_make_insight("i1")]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 1])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=signals)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {}, {})),
            f"{_R}.synthesize": MagicMock(return_value=insights),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
        }

        with _PatchCtx(overrides) as ctx:
            result = run_pipeline(stages=["fetch", "synthesize"])

        assert result.signals_fetched == 1
        assert result.insights_generated == 1
        assert result.ideas_generated == 0
        ctx.mocks["ideate"].assert_not_called()
        ctx.mocks["evaluate"].assert_not_called()

    def test_skip_annotate_stage(self):
        """When 'annotate' is not in stages, annotate_signals is not called."""
        signals = [_make_signal("s1")]
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 1])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {}, {})),
        }

        with _PatchCtx(overrides) as ctx:
            result = run_pipeline(stages=["fetch"])

        ctx.mocks["annotate_signals"].assert_not_called()
        assert result.signals_fetched == 1

    def test_invalid_stage_raises_error(self):
        """Requesting an unknown stage raises ValueError."""
        with _PatchCtx():
            with pytest.raises(ValueError, match="Unknown stages"):
                run_pipeline(stages=["fetch", "bogus_stage"])

    def test_stages_execute_in_pipeline_order(self):
        """Even if stages are passed out of order, they execute in pipeline order."""
        call_order = []
        signals = [_make_signal("s1")]
        insights = [_make_insight("i1")]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 1])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=signals)

        def track(name, return_value=None):
            def side_effect(*args, **kwargs):
                call_order.append(name)
                return return_value
            return side_effect

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(side_effect=track("fetch", (signals, {}, {}))),
            f"{_R}.annotate_signals": MagicMock(side_effect=track("annotate")),
            f"{_R}.synthesize": MagicMock(side_effect=track("synthesize", insights)),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
            f"{_R}.triangulate": MagicMock(return_value=[]),
            f"{_R}.format_cluster_context": MagicMock(return_value=None),
        }

        # Pass stages in reverse order
        with _PatchCtx(overrides):
            run_pipeline(stages=["synthesize", "annotate", "fetch"])

        assert call_order == ["fetch", "annotate", "synthesize"]


# ═══════════════════════════════════════════════════════════════════════
# 4. Partial adapter failure
# ═══════════════════════════════════════════════════════════════════════


class TestPartialAdapterFailure:
    """Test pipeline behavior when one source adapter fails."""

    def test_partial_failure_returns_successful_signals(self):
        """When one adapter fails, signals from others are still processed."""
        # Simulate: source_a returns signals, source_b fails
        # The runner's _fetch_all_signals handles failures internally,
        # so we mock it to return only the successful signals + error metrics
        successful_signals = [
            _make_signal("sa1", adapter="mock_source_a"),
            _make_signal("sa2", adapter="mock_source_a"),
        ]
        insights = [_make_insight("i1")]
        units = [_make_unit("u1")]

        adapter_metrics = {
            "mock_source_a": {"status": "ok", "signal_count": 2, "error_message": None, "duration_ms": 50},
            "mock_source_b": {"status": "error", "signal_count": 0, "error_message": "Connection refused", "duration_ms": 5},
        }

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 2])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=successful_signals)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(
                return_value=(successful_signals, {"mock_source_a": 5, "mock_source_b": 5}, adapter_metrics)
            ),
            f"{_R}.synthesize": MagicMock(return_value=insights),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
            f"{_R}.ideate": MagicMock(return_value=units),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=units, duplicates=0)),
            f"{_R}.evaluate": MagicMock(return_value=_make_evaluation("u1", score=80.0)),
        }

        with _PatchCtx(overrides):
            result = run_pipeline(signal_limit=10, min_score=50.0)

        assert result.signals_fetched == 2
        assert result.insights_generated == 1
        assert result.ideas_generated == 1
        assert result.ideas_evaluated == 1
        # Adapter metrics reflect the failure
        assert result.adapter_metrics["mock_source_a"]["status"] == "ok"
        assert result.adapter_metrics["mock_source_b"]["status"] == "error"

    def test_all_adapters_fail_produces_zero_signals(self):
        """When all adapters fail, pipeline continues with 0 signals."""
        adapter_metrics = {
            "source_a": {"status": "error", "signal_count": 0, "error_message": "Timeout", "duration_ms": 10},
            "source_b": {"status": "circuit_open", "signal_count": 0, "error_message": "Circuit open", "duration_ms": 0},
        }

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(
                return_value=([], {"source_a": 5, "source_b": 5}, adapter_metrics)
            ),
        }

        with _PatchCtx(overrides) as ctx:
            result = run_pipeline()

        assert result.signals_fetched == 0
        assert result.signals_new == 0
        assert result.insights_generated == 0
        assert result.ideas_generated == 0
        # Synthesis not called since no unsynthesized signals
        ctx.mocks["synthesize"].assert_not_called()

    def test_circuit_breaker_adapter_recorded_in_metrics(self):
        """An adapter with circuit_open status appears in adapter_metrics."""
        adapter_metrics = {
            "good_source": {"status": "ok", "signal_count": 3, "error_message": None, "duration_ms": 100},
            "tripped_source": {"status": "circuit_open", "signal_count": 0, "error_message": "circuit breaker open, retry in 300s", "duration_ms": 0},
        }
        signals = [_make_signal("s1", adapter="good_source")]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 1])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(
                return_value=(signals, {"good_source": 5, "tripped_source": 5}, adapter_metrics)
            ),
        }

        with _PatchCtx(overrides):
            result = run_pipeline()

        assert result.adapter_metrics["tripped_source"]["status"] == "circuit_open"
        assert result.adapter_metrics["good_source"]["status"] == "ok"
        assert result.signals_fetched == 1


# ═══════════════════════════════════════════════════════════════════════
# 5. Zero signals
# ═══════════════════════════════════════════════════════════════════════


class TestZeroSignals:
    """Test pipeline behavior with zero signals returned."""

    def test_zero_signals_returns_empty_result(self):
        """No signals → all downstream stages produce zero output."""
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=([], {}, {})),
        }

        with _PatchCtx(overrides) as ctx:
            result = run_pipeline()

        assert isinstance(result, PipelineResult)
        assert result.signals_fetched == 0
        assert result.signals_new == 0
        assert result.insights_generated == 0
        assert result.ideas_generated == 0
        assert result.ideas_evaluated == 0
        assert result.top_ideas == []
        assert result.avg_insight_confidence == 0.0
        assert result.avg_idea_score == 0.0

    def test_zero_signals_skips_annotation(self):
        """annotate_signals is not called when there are no signals."""
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=([], {}, {})),
        }

        with _PatchCtx(overrides) as ctx:
            run_pipeline()

        # annotate_signals only called when signals exist
        ctx.mocks["annotate_signals"].assert_not_called()

    def test_zero_signals_store_still_closed(self):
        """Even with no signals, store.close() is called in finally block."""
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=([], {}, {})),
        }

        with _PatchCtx(overrides):
            run_pipeline()

        mock_store.close.assert_called_once()

    def test_zero_signals_pipeline_run_still_recorded(self):
        """Pipeline run is inserted and updated even when no signals."""
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=([], {}, {})),
        }

        with _PatchCtx(overrides):
            result = run_pipeline()

        mock_store.insert_pipeline_run.assert_called_once()
        mock_store.update_pipeline_run.assert_called_once()
        assert result.run_id.startswith("run-")

    def test_zero_unsynthesized_signals_skips_synthesis(self):
        """When all signals are already synthesized, synthesis engine is not called."""
        signals = [_make_signal("s1"), _make_signal("s2")]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 2])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=[])  # All already synthesized

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {}, {})),
        }

        with _PatchCtx(overrides) as ctx:
            result = run_pipeline()

        ctx.mocks["synthesize"].assert_not_called()
        assert result.signals_fetched == 2
        assert result.signals_skipped == 2
        assert result.insights_generated == 0
