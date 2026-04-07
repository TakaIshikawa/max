"""Tests for pipeline runner orchestration logic.

Tests the runner's orchestration — stage ordering, conditional branching,
metric computation, and error handling — with all LLM-dependent engines
and source adapters mocked at the function boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from max.analysis.triangulation import SignalCluster
from max.pipeline.dedup import DedupResult
from max.pipeline.runner import PipelineResult, _fetch_all_signals, run_pipeline
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType
from max.types.tact_spec import (
    TactArchitecture,
    TactGoal,
    TactProduct,
    TactRequirement,
    TactSpec,
    TactTechStack,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_signal(id: str, adapter: str = "hackernews", **kw) -> Signal:
    defaults = dict(
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"Signal {id}",
        content=f"Content for {id}",
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
        strengths=["good"],
        weaknesses=["bad"],
        recommendation="yes" if score >= 60 else "no",
        weights_used={"pain_severity": 0.2},
    )


def _make_spec(unit_id: str, name: str = "test-spec") -> TactSpec:
    return TactSpec(
        buildable_unit_id=unit_id,
        product=TactProduct(
            name=name,
            vision="Test vision",
            goals=[TactGoal(id="G-1", description="Goal", success_criteria="Done")],
            tech_stack=TactTechStack(languages=["Python"], frameworks=[], infrastructure=[]),
            constraints=[],
        ),
        architecture=TactArchitecture(patterns=[], invariants=[], conventions=[]),
        requirements=[
            TactRequirement(
                title="Req",
                priority="critical",
                description="Desc",
                acceptance_criteria=["AC1"],
            ),
        ],
    )


def _make_cluster(
    topic: str,
    signals: list[Signal],
    source_diversity: float = 0.5,
) -> SignalCluster:
    roles: dict[str, int] = {}
    for s in signals:
        role = s.signal_role or "unknown"
        roles[role] = roles.get(role, 0) + 1
    return SignalCluster(
        topic=topic,
        signals=signals,
        source_diversity=source_diversity,
        avg_credibility=0.7,
        roles=roles,
        centroid=[],
    )


# ── Patch targets (runner module) ────────────────────────────────────

_R = "max.pipeline.runner"


def _base_patches(mock_store: MagicMock) -> dict[str, MagicMock | object]:
    """Return a dict of patch target -> mock for all external deps in the runner."""
    return {
        f"{_R}.Store": MagicMock(return_value=mock_store),
        f"{_R}.SemanticIndex": MagicMock(),
        f"{_R}.token_tracker": MagicMock(reset=MagicMock(), summary=MagicMock(return_value={"input": 100, "output": 200})),
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
        f"{_R}.generate_spec": MagicMock(),
        f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=[], duplicates=0)),
        f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=[], duplicates=0)),
        f"{_R}.write_tact_spec": MagicMock(),
        f"{_R}._fetch_all_signals": MagicMock(return_value=([], {})),
    }


def _make_mock_store() -> MagicMock:
    """Build a mock Store with all methods the runner calls."""
    store = MagicMock()
    store.insert_pipeline_run = MagicMock()
    store.update_pipeline_run = MagicMock()
    store.get_feedback_outcomes = MagicMock(return_value=[])
    store.count_signals = MagicMock(side_effect=[0, 0])  # pre, post
    store.insert_signal = MagicMock()
    store.get_unsynthesized_signals = MagicMock(return_value=[])
    store.mark_signals_synthesized = MagicMock()
    store.get_insights = MagicMock(return_value=[])
    store.insert_insight = MagicMock()
    store.get_buildable_units = MagicMock(return_value=[])
    store.insert_buildable_unit = MagicMock()
    store.update_buildable_unit_status = MagicMock()
    store.insert_evaluation = MagicMock()
    store.insert_tact_spec = MagicMock()
    store.close = MagicMock()
    store.get_signal = MagicMock(return_value=None)
    store.get_insight = MagicMock(return_value=None)
    return store


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
            # Store by short key: last part of dotted path
            short = target.rsplit(".", 1)[-1]
            self.mocks[short] = started
        return self

    def __exit__(self, *args):
        for p in self._patchers:
            p.stop()


# ═══════════════════════════════════════════════════════════════════════
# 1. run_pipeline() end-to-end flow
# ═══════════════════════════════════════════════════════════════════════


class TestRunPipelineEndToEnd:
    """Verify the pipeline calls each stage in order and returns a correct PipelineResult."""

    def test_calls_stages_in_order(self):
        """Pipeline calls fetch → annotate → triangulate → synthesize → ideate → evaluate → spec."""
        signals = [_make_signal("s1"), _make_signal("s2")]
        insights = [_make_insight("i1", evidence=["s1"])]
        units = [_make_unit("u1", insights=["i1"])]
        evaluation = _make_evaluation("u1", score=80.0)
        spec = _make_spec("u1")

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 2])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=signals)
        mock_store.get_insights = MagicMock(return_value=[])
        mock_store.get_buildable_units = MagicMock(return_value=[])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {"hn": 2})),
            f"{_R}.synthesize": MagicMock(return_value=insights),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=units, duplicates=0)),
            f"{_R}.ideate": MagicMock(return_value=units),
            f"{_R}.evaluate": MagicMock(return_value=evaluation),
            f"{_R}.generate_spec": MagicMock(return_value=spec),
            f"{_R}.triangulate": MagicMock(return_value=[]),
        }

        with _PatchCtx(overrides) as ctx:
            result = run_pipeline(signal_limit=10, min_score=50.0)

        assert isinstance(result, PipelineResult)
        assert result.signals_fetched == 2
        assert result.signals_new == 2
        assert result.insights_generated == 1
        assert result.ideas_generated == 1
        assert result.ideas_evaluated == 1
        assert result.specs_generated == 1

    def test_returns_pipeline_result_type(self):
        with _PatchCtx():
            result = run_pipeline()
        assert isinstance(result, PipelineResult)

    def test_empty_pipeline_returns_zero_metrics(self):
        """No signals → all counters zero."""
        with _PatchCtx():
            result = run_pipeline()

        assert result.signals_fetched == 0
        assert result.insights_generated == 0
        assert result.ideas_generated == 0
        assert result.specs_generated == 0


# ═══════════════════════════════════════════════════════════════════════
# 2. _fetch_all_signals()
# ═══════════════════════════════════════════════════════════════════════


class TestFetchAllSignals:
    """Test signal fetching, aggregation, error handling, and adaptive allocation."""

    def test_aggregates_signals_from_multiple_adapters(self):
        adapter_a = MagicMock(name="adapter_a")
        adapter_a.name = "adapter_a"
        adapter_a.fetch = MagicMock(return_value=[_make_signal("a1", adapter="adapter_a")])

        adapter_b = MagicMock(name="adapter_b")
        adapter_b.name = "adapter_b"
        adapter_b.fetch = MagicMock(return_value=[_make_signal("b1", adapter="adapter_b")])

        with (
            patch(f"{_R}.get_all_adapters", return_value=[adapter_a, adapter_b]),
            patch(f"{_R}.asyncio.run", side_effect=lambda coro: coro),
        ):
            # fetch is already returning list directly (mock), asyncio.run just passes through
            adapter_a.fetch = MagicMock(return_value=[_make_signal("a1")])
            adapter_b.fetch = MagicMock(return_value=[_make_signal("b1")])
            with patch(f"{_R}.asyncio.run", side_effect=[
                [_make_signal("a1")],
                [_make_signal("b1")],
            ]):
                signals, alloc = _fetch_all_signals(signal_limit=10)

        assert len(signals) == 2
        assert alloc["adapter_a"] > 0
        assert alloc["adapter_b"] > 0

    def test_adapter_failure_caught_not_raised(self, capsys):
        """If one adapter raises, the other's signals are still returned."""
        adapter_ok = MagicMock()
        adapter_ok.name = "ok_adapter"

        adapter_fail = MagicMock()
        adapter_fail.name = "fail_adapter"

        with (
            patch(f"{_R}.get_all_adapters", return_value=[adapter_ok, adapter_fail]),
            patch(f"{_R}.asyncio.run", side_effect=[
                [_make_signal("ok1")],
                RuntimeError("network down"),
            ]),
        ):
            signals, alloc = _fetch_all_signals(signal_limit=10)

        assert len(signals) == 1
        assert signals[0].id == "ok1"
        captured = capsys.readouterr()
        assert "fail_adapter" in captured.out
        assert "network down" in captured.out

    def test_adaptive_allocation_with_store(self):
        """When store is provided, compute_fetch_allocation is called."""
        adapter = MagicMock()
        adapter.name = "test_adapter"
        mock_store = _make_mock_store()

        with (
            patch(f"{_R}.get_all_adapters", return_value=[adapter]),
            patch("max.pipeline.fetch_strategy.compute_fetch_allocation", return_value={"test_adapter": 15}) as mock_alloc,
            patch(f"{_R}.asyncio.run", return_value=[_make_signal("s1")]),
        ):
            signals, alloc = _fetch_all_signals(signal_limit=30, store=mock_store)

        mock_alloc.assert_called_once_with(30, ["test_adapter"], mock_store)
        assert alloc == {"test_adapter": 15}

    def test_uniform_allocation_without_store(self):
        """Without store, signals are split evenly among adapters."""
        adapters = [MagicMock(name=f"a{i}") for i in range(3)]
        for i, a in enumerate(adapters):
            a.name = f"a{i}"

        with (
            patch(f"{_R}.get_all_adapters", return_value=adapters),
            patch(f"{_R}.asyncio.run", return_value=[]),
        ):
            _, alloc = _fetch_all_signals(signal_limit=30)

        assert alloc == {"a0": 10, "a1": 10, "a2": 10}


# ═══════════════════════════════════════════════════════════════════════
# 3. Signal role annotation
# ═══════════════════════════════════════════════════════════════════════


class TestSignalRoleAnnotation:
    """Verify annotate_signals is called after fetching, before storing."""

    def test_annotate_signals_called_with_fetched_signals(self):
        signals = [_make_signal("s1"), _make_signal("s2")]
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 2])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=[])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {})),
        }

        with _PatchCtx(overrides) as ctx:
            run_pipeline()

        ctx.mocks["annotate_signals"].assert_called_once_with(signals)

    def test_signals_inserted_after_annotation(self):
        """annotate_signals is called before insert_signal."""
        call_order = []
        signals = [_make_signal("s1")]

        mock_annotate = MagicMock(side_effect=lambda s: call_order.append("annotate"))
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 1])
        mock_store.insert_signal = MagicMock(side_effect=lambda s: call_order.append("insert"))
        mock_store.get_unsynthesized_signals = MagicMock(return_value=[])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {})),
            f"{_R}.annotate_signals": mock_annotate,
        }

        with _PatchCtx(overrides):
            run_pipeline()

        assert call_order == ["annotate", "insert"]


# ═══════════════════════════════════════════════════════════════════════
# 4. Incremental synthesis
# ═══════════════════════════════════════════════════════════════════════


class TestIncrementalSynthesis:
    """Verify only unsynthesized signals go to synthesis, and are marked afterward."""

    def test_only_unsynthesized_signals_passed(self):
        all_signals = [_make_signal("s1"), _make_signal("s2"), _make_signal("s3")]
        unsynthesized = [_make_signal("s2"), _make_signal("s3")]
        insights = [_make_insight("i1")]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 3])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=unsynthesized)

        mock_synthesize = MagicMock(return_value=insights)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(all_signals, {})),
            f"{_R}.synthesize": mock_synthesize,
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
        }

        with _PatchCtx(overrides) as ctx:
            result = run_pipeline()

        # synthesize received only unsynthesized signals
        mock_synthesize.assert_called_once()
        passed_signals = mock_synthesize.call_args[0][0]
        assert len(passed_signals) == 2
        assert {s.id for s in passed_signals} == {"s2", "s3"}

        # Skipped count reflects the difference
        assert result.signals_skipped == 1  # 3 fetched - 2 unsynthesized

    def test_signals_marked_synthesized_after_synthesis(self):
        unsynthesized = [_make_signal("s1"), _make_signal("s2")]
        insights = [_make_insight("i1")]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 2])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=unsynthesized)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(unsynthesized, {})),
            f"{_R}.synthesize": MagicMock(return_value=insights),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
        }

        with _PatchCtx(overrides):
            run_pipeline()

        mock_store.mark_signals_synthesized.assert_called_once_with(["s1", "s2"])

    def test_no_synthesis_when_all_signals_already_synthesized(self):
        """When get_unsynthesized_signals returns empty, synthesize is not called."""
        signals = [_make_signal("s1")]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 1])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=[])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {})),
        }

        with _PatchCtx(overrides) as ctx:
            result = run_pipeline()

        ctx.mocks["synthesize"].assert_not_called()
        assert result.insights_generated == 0
        assert result.signals_skipped == 1


# ═══════════════════════════════════════════════════════════════════════
# 5. Triangulation integration
# ═══════════════════════════════════════════════════════════════════════


class TestTriangulationIntegration:
    """Verify triangulate_signals is called and cluster context is passed to synthesis."""

    def test_triangulate_called_with_new_signals(self):
        signals = [_make_signal("s1"), _make_signal("s2")]
        insights = [_make_insight("i1")]
        clusters = [
            _make_cluster("topic1", signals),
        ]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 2])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=signals)

        mock_triangulate = MagicMock(return_value=clusters)
        mock_format = MagicMock(return_value="Cluster context text")
        mock_synthesize = MagicMock(return_value=insights)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {})),
            f"{_R}.triangulate": mock_triangulate,
            f"{_R}.format_cluster_context": mock_format,
            f"{_R}.synthesize": mock_synthesize,
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
        }

        with _PatchCtx(overrides):
            result = run_pipeline()

        mock_triangulate.assert_called_once_with(signals)
        mock_format.assert_called_once_with(clusters)
        # cluster_context is passed through to synthesize
        _, kwargs = mock_synthesize.call_args
        assert kwargs["cluster_context"] == "Cluster context text"

    def test_multi_source_cluster_count(self):
        """Clusters with >1 distinct source are counted in multi_source_clusters."""
        s1 = _make_signal("s1", adapter="hn")
        s2 = _make_signal("s2", adapter="npm")
        s3 = _make_signal("s3", adapter="hn")

        multi = _make_cluster("multi", [s1, s2])
        single = _make_cluster("single", [s3])

        # Override distinct_sources property for test clarity
        # SignalCluster.distinct_sources = {s.source_adapter for s in signals}
        # multi has {"hn", "npm"} → len > 1; single has {"hn"} → len == 1

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 3])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=[s1, s2, s3])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=([s1, s2, s3], {})),
            f"{_R}.triangulate": MagicMock(return_value=[multi, single]),
            f"{_R}.synthesize": MagicMock(return_value=[]),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=[], duplicates=0)),
        }

        with _PatchCtx(overrides):
            result = run_pipeline()

        assert result.clusters_found == 2
        assert result.multi_source_clusters == 1


# ═══════════════════════════════════════════════════════════════════════
# 6. Gap detection
# ═══════════════════════════════════════════════════════════════════════


class TestGapDetection:
    """Verify detect_gaps is called and results flow to ideation."""

    def test_detect_gaps_called_with_store(self):
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        mock_detect = MagicMock(return_value=[])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}.detect_gaps": mock_detect,
        }

        with _PatchCtx(overrides):
            run_pipeline()

        mock_detect.assert_called_once_with(mock_store)

    def test_gaps_detected_metric(self):
        mock_gaps = [MagicMock(), MagicMock(), MagicMock()]
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}.detect_gaps": MagicMock(return_value=mock_gaps),
            f"{_R}.format_gaps_for_ideation": MagicMock(return_value="gaps text"),
        }

        with _PatchCtx(overrides):
            result = run_pipeline()

        assert result.gaps_detected == 3

    def test_gaps_context_passed_to_ideation(self):
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        mock_ideate = MagicMock(return_value=[])

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}.detect_gaps": MagicMock(return_value=[MagicMock()]),
            f"{_R}.format_gaps_for_ideation": MagicMock(return_value="GAPS CONTEXT"),
            f"{_R}.ideate": mock_ideate,
        }

        with _PatchCtx(overrides):
            run_pipeline(ideation_mode="direct")

        _, kwargs = mock_ideate.call_args
        assert kwargs["gaps_context"] == "GAPS CONTEXT"


# ═══════════════════════════════════════════════════════════════════════
# 7. Ideation modes
# ═══════════════════════════════════════════════════════════════════════


class TestIdeationModes:
    """Test that ideation_mode routes to the correct engine function(s)."""

    def _run_with_mode(self, mode: str) -> _PatchCtx:
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])
        mock_store.get_buildable_units = MagicMock(return_value=[_make_unit("existing")])

        ctx = _PatchCtx({
            f"{_R}.Store": MagicMock(return_value=mock_store),
        })
        ctx.__enter__()
        run_pipeline(ideation_mode=mode)
        return ctx

    def test_direct_mode(self):
        ctx = self._run_with_mode("direct")
        try:
            ctx.mocks["ideate"].assert_called_once()
            ctx.mocks["ideate_refinement"].assert_not_called()
            ctx.mocks["ideate_cross_domain"].assert_not_called()
        finally:
            ctx.__exit__(None, None, None)

    def test_refinement_mode(self):
        ctx = self._run_with_mode("refinement")
        try:
            ctx.mocks["ideate"].assert_not_called()
            ctx.mocks["ideate_refinement"].assert_called_once()
            ctx.mocks["ideate_cross_domain"].assert_not_called()
        finally:
            ctx.__exit__(None, None, None)

    def test_cross_domain_mode(self):
        ctx = self._run_with_mode("cross_domain")
        try:
            ctx.mocks["ideate"].assert_not_called()
            ctx.mocks["ideate_refinement"].assert_not_called()
            ctx.mocks["ideate_cross_domain"].assert_called_once()
        finally:
            ctx.__exit__(None, None, None)

    def test_all_mode_calls_all_engines(self):
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])
        mock_store.get_buildable_units = MagicMock(return_value=[_make_unit("existing")])

        with _PatchCtx({f"{_R}.Store": MagicMock(return_value=mock_store)}) as ctx:
            run_pipeline(ideation_mode="all")

        ctx.mocks["ideate"].assert_called_once()
        ctx.mocks["ideate_refinement"].assert_called_once()
        ctx.mocks["ideate_cross_domain"].assert_called_once()

    def test_refinement_skipped_when_no_evaluated_units(self):
        """refinement mode skips ideate_refinement when store has no evaluated units."""
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])
        # get_buildable_units(status="evaluated") returns empty
        mock_store.get_buildable_units = MagicMock(return_value=[])

        with _PatchCtx({f"{_R}.Store": MagicMock(return_value=mock_store)}) as ctx:
            run_pipeline(ideation_mode="refinement")

        ctx.mocks["ideate_refinement"].assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# 8. Filtering by min_score
# ═══════════════════════════════════════════════════════════════════════


class TestMinScoreFiltering:
    """Verify that only ideas above min_score get specs generated."""

    def test_only_above_threshold_get_specs(self):
        units = [_make_unit("u1"), _make_unit("u2"), _make_unit("u3")]
        evals = [
            _make_evaluation("u1", score=90.0),
            _make_evaluation("u2", score=40.0),  # below 50.0 threshold
            _make_evaluation("u3", score=70.0),
        ]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        eval_iter = iter(evals)
        mock_evaluate = MagicMock(side_effect=lambda unit, **kw: next(eval_iter))
        mock_generate_spec = MagicMock(side_effect=lambda u, e: _make_spec(u.id, u.title))

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=units, duplicates=0)),
            f"{_R}.ideate": MagicMock(return_value=units),
            f"{_R}.evaluate": mock_evaluate,
            f"{_R}.generate_spec": mock_generate_spec,
        }

        with _PatchCtx(overrides):
            result = run_pipeline(min_score=50.0)

        assert result.ideas_evaluated == 3
        assert result.specs_generated == 2  # u1 (90) and u3 (70) pass, u2 (40) fails
        assert mock_generate_spec.call_count == 2

    def test_no_specs_when_all_below_threshold(self):
        units = [_make_unit("u1")]
        evals = [_make_evaluation("u1", score=30.0)]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        mock_generate_spec = MagicMock()

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=units, duplicates=0)),
            f"{_R}.ideate": MagicMock(return_value=units),
            f"{_R}.evaluate": MagicMock(return_value=evals[0]),
            f"{_R}.generate_spec": mock_generate_spec,
        }

        with _PatchCtx(overrides):
            result = run_pipeline(min_score=50.0)

        assert result.specs_generated == 0
        mock_generate_spec.assert_not_called()

    def test_unit_status_approved_only_for_passing(self):
        """Units above threshold get status='approved', others stay at 'evaluated'."""
        units = [_make_unit("u_pass"), _make_unit("u_fail")]
        evals = [
            _make_evaluation("u_pass", score=80.0),
            _make_evaluation("u_fail", score=30.0),
        ]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        eval_iter = iter(evals)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=units, duplicates=0)),
            f"{_R}.ideate": MagicMock(return_value=units),
            f"{_R}.evaluate": MagicMock(side_effect=lambda unit, **kw: next(eval_iter)),
            f"{_R}.generate_spec": MagicMock(side_effect=lambda u, e: _make_spec(u.id)),
        }

        with _PatchCtx(overrides):
            run_pipeline(min_score=50.0)

        status_calls = mock_store.update_buildable_unit_status.call_args_list
        # Both get "evaluated" after evaluate(), but only u_pass gets "approved"
        statuses = [(c[0][0], c[0][1]) for c in status_calls]
        assert ("u_pass", "evaluated") in statuses
        assert ("u_fail", "evaluated") in statuses
        assert ("u_pass", "approved") in statuses
        assert ("u_fail", "approved") not in statuses


# ═══════════════════════════════════════════════════════════════════════
# 9. PipelineResult metrics
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineResultMetrics:
    """Verify token_usage, avg_insight_confidence, avg_idea_score are computed correctly."""

    def test_token_usage_from_tracker(self):
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        token_summary = {"input": 500, "output": 300}

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}.token_tracker": MagicMock(
                reset=MagicMock(),
                summary=MagicMock(return_value=token_summary),
            ),
        }

        with _PatchCtx(overrides):
            result = run_pipeline()

        assert result.token_usage == {"input": 500, "output": 300}

    def test_avg_insight_confidence_computed(self):
        signals = [_make_signal("s1")]
        insights = [
            _make_insight("i1", confidence=0.9),
            _make_insight("i2", confidence=0.7),
            _make_insight("i3", confidence=0.5),
        ]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 1])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=signals)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {})),
            f"{_R}.synthesize": MagicMock(return_value=insights),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
        }

        with _PatchCtx(overrides):
            result = run_pipeline()

        expected_avg = (0.9 + 0.7 + 0.5) / 3
        assert abs(result.avg_insight_confidence - expected_avg) < 1e-9

    def test_avg_idea_score_computed(self):
        units = [_make_unit("u1"), _make_unit("u2")]
        evals = [
            _make_evaluation("u1", score=80.0),
            _make_evaluation("u2", score=60.0),
        ]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        eval_iter = iter(evals)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=units, duplicates=0)),
            f"{_R}.ideate": MagicMock(return_value=units),
            f"{_R}.evaluate": MagicMock(side_effect=lambda unit, **kw: next(eval_iter)),
            f"{_R}.generate_spec": MagicMock(side_effect=lambda u, e: _make_spec(u.id)),
        }

        with _PatchCtx(overrides):
            result = run_pipeline(min_score=50.0)

        assert result.avg_idea_score == pytest.approx(70.0)

    def test_avg_confidence_zero_when_no_insights(self):
        with _PatchCtx():
            result = run_pipeline()
        assert result.avg_insight_confidence == 0.0

    def test_avg_idea_score_zero_when_no_ideas(self):
        with _PatchCtx():
            result = run_pipeline()
        assert result.avg_idea_score == 0.0

    def test_top_ideas_capped_at_five(self):
        units = [_make_unit(f"u{i}") for i in range(7)]
        evals = [_make_evaluation(f"u{i}", score=50.0 + i * 5) for i in range(7)]

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        eval_iter = iter(evals)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=units, duplicates=0)),
            f"{_R}.ideate": MagicMock(return_value=units),
            f"{_R}.evaluate": MagicMock(side_effect=lambda unit, **kw: next(eval_iter)),
            f"{_R}.generate_spec": MagicMock(side_effect=lambda u, e: _make_spec(u.id)),
        }

        with _PatchCtx(overrides):
            result = run_pipeline(min_score=0.0)

        assert len(result.top_ideas) == 5
        # Top ideas sorted by score descending
        scores = [t["score"] for t in result.top_ideas]
        assert scores == sorted(scores, reverse=True)


# ═══════════════════════════════════════════════════════════════════════
# 10. Pipeline run recording
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineRunRecording:
    """Verify insert_pipeline_run and update_pipeline_run are called correctly."""

    def test_insert_pipeline_run_called_with_config(self):
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        overrides = {f"{_R}.Store": MagicMock(return_value=mock_store)}

        with _PatchCtx(overrides):
            result = run_pipeline(signal_limit=20, min_score=55.0, weight_profile="aggressive")

        mock_store.insert_pipeline_run.assert_called_once()
        run_id, config = mock_store.insert_pipeline_run.call_args[0]
        assert run_id.startswith("run-")
        assert config["signal_limit"] == 20
        assert config["min_score"] == 55.0
        assert config["weight_profile"] == "aggressive"
        assert config["ideation_mode"] == "direct"
        assert config["profile"] is None

    def test_update_pipeline_run_called_in_finally(self):
        """update_pipeline_run is called even if the pipeline raises."""
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        # Make _fetch_all_signals raise after some work
        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(side_effect=RuntimeError("boom")),
        }

        with _PatchCtx(overrides):
            with pytest.raises(RuntimeError, match="boom"):
                run_pipeline()

        # update_pipeline_run still called (in finally block)
        mock_store.update_pipeline_run.assert_called_once()
        mock_store.close.assert_called_once()

    def test_update_pipeline_run_receives_metrics(self):
        signals = [_make_signal("s1")]
        insights = [_make_insight("i1", confidence=0.85)]
        units = [_make_unit("u1")]
        evaluation = _make_evaluation("u1", score=75.0)

        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 1])
        mock_store.get_unsynthesized_signals = MagicMock(return_value=signals)

        overrides = {
            f"{_R}.Store": MagicMock(return_value=mock_store),
            f"{_R}._fetch_all_signals": MagicMock(return_value=(signals, {"hn": 1})),
            f"{_R}.synthesize": MagicMock(return_value=insights),
            f"{_R}.dedup_insights": MagicMock(return_value=DedupResult(kept=insights, duplicates=0)),
            f"{_R}.dedup_buildable_units": MagicMock(return_value=DedupResult(kept=units, duplicates=0)),
            f"{_R}.ideate": MagicMock(return_value=units),
            f"{_R}.evaluate": MagicMock(return_value=evaluation),
            f"{_R}.generate_spec": MagicMock(return_value=_make_spec("u1")),
        }

        with _PatchCtx(overrides):
            result = run_pipeline(min_score=50.0)

        mock_store.update_pipeline_run.assert_called_once()
        _, kwargs = mock_store.update_pipeline_run.call_args
        assert kwargs["signals_fetched"] == 1
        assert kwargs["signals_new"] == 1
        assert kwargs["insights_generated"] == 1
        assert kwargs["ideas_generated"] == 1
        assert kwargs["ideas_evaluated"] == 1
        assert kwargs["specs_generated"] == 1
        assert kwargs["avg_idea_score"] == 75.0

    def test_run_id_stored_in_result(self):
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        overrides = {f"{_R}.Store": MagicMock(return_value=mock_store)}

        with _PatchCtx(overrides):
            result = run_pipeline()

        assert result.run_id.startswith("run-")
        assert len(result.run_id) > 4  # "run-" + hex

    def test_store_closed_in_finally(self):
        mock_store = _make_mock_store()
        mock_store.count_signals = MagicMock(side_effect=[0, 0])

        overrides = {f"{_R}.Store": MagicMock(return_value=mock_store)}

        with _PatchCtx(overrides):
            run_pipeline()

        mock_store.close.assert_called_once()
