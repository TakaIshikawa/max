"""Comprehensive tests for Store CRUD operations and analytics methods.

Covers methods and edge cases not exercised by test_store.py or test_attribution.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType
from max.types.tact_spec import TactSpec


# ── Helpers ──────────────────────────────────────────────────────────


def _make_signal(
    adapter: str = "hackernews",
    sig_id: str = "",
    url: str = "",
    *,
    source_type: SignalSourceType = SignalSourceType.FORUM,
    metadata: dict | None = None,
) -> Signal:
    sid = sig_id or f"sig-{adapter}-001"
    return Signal(
        id=sid,
        source_type=source_type,
        source_adapter=adapter,
        title=f"Signal from {adapter}",
        content=f"Content from {adapter}",
        url=url or f"https://example.com/{sid}",
        credibility=0.7,
        metadata=metadata or {},
    )


def _make_score(value: float = 7.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _make_unit(
    unit_id: str = "bu-test001",
    evidence_signals: list[str] | None = None,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Unit {unit_id}",
        one_liner="Test unit",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        target_users="both",
        value_proposition="Test value",
        evidence_signals=evidence_signals or [],
    )


def _make_evaluation(unit_id: str = "bu-test001", overall_score: float = 72.0) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_make_score(8.0),
        addressable_scale=_make_score(7.0),
        build_effort=_make_score(6.0),
        composability=_make_score(7.5),
        competitive_density=_make_score(8.0),
        timing_fit=_make_score(7.0),
        compounding_value=_make_score(6.5),
        overall_score=overall_score,
        strengths=["test"],
        weaknesses=["test"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )


# ── Signal operations ────────────────────────────────────────────────


class TestSignalOperations:
    def test_insert_signal_auto_generates_id(self, store: Store) -> None:
        sig = Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter="hackernews",
            title="Auto ID test",
            content="content",
            url="https://example.com/auto-id",
        )
        assert sig.id == ""
        stored = store.insert_signal(sig)
        assert stored.id.startswith("sig-")
        assert len(stored.id) > 4

    def test_insert_signal_preserves_explicit_id(self, store: Store) -> None:
        sig = _make_signal(sig_id="sig-explicit-123")
        stored = store.insert_signal(sig)
        assert stored.id == "sig-explicit-123"

    def test_insert_signal_duplicate_url_is_silent(self, store: Store) -> None:
        sig1 = _make_signal(sig_id="sig-a", url="https://example.com/dup")
        sig2 = _make_signal(sig_id="sig-b", url="https://example.com/dup")
        store.insert_signal(sig1)
        store.insert_signal(sig2)
        assert store.count_signals() == 1
        # The first insert wins
        assert store.get_signal("sig-a") is not None
        assert store.get_signal("sig-b") is None

    def test_get_signals_respects_limit(self, store: Store) -> None:
        for i in range(5):
            store.insert_signal(_make_signal(sig_id=f"sig-lim-{i}", url=f"https://example.com/lim-{i}"))
        signals = store.get_signals(limit=3)
        assert len(signals) == 3

    def test_get_signals_with_source_type_filter(self, store: Store) -> None:
        store.insert_signal(_make_signal(adapter="hn", sig_id="sig-forum", source_type=SignalSourceType.FORUM))
        store.insert_signal(_make_signal(adapter="npm", sig_id="sig-reg", url="https://npm.io/pkg", source_type=SignalSourceType.REGISTRY))
        assert len(store.get_signals(source_type="forum")) == 1
        assert len(store.get_signals(source_type="registry")) == 1
        assert len(store.get_signals(source_type="security")) == 0

    def test_get_signals_no_filter_returns_all(self, store: Store) -> None:
        store.insert_signal(_make_signal(sig_id="sig-1", url="https://a.com/1"))
        store.insert_signal(_make_signal(sig_id="sig-2", url="https://a.com/2"))
        assert len(store.get_signals()) == 2

    def test_count_signals_empty(self, store: Store) -> None:
        assert store.count_signals() == 0

    def test_get_signal_not_found(self, store: Store) -> None:
        assert store.get_signal("nonexistent") is None


class TestSynthesizedSignals:
    def test_unsynthesized_returns_all_initially(self, store: Store, sample_signal: Signal) -> None:
        store.insert_signal(sample_signal)
        unsynthesized = store.get_unsynthesized_signals()
        assert len(unsynthesized) == 1
        assert unsynthesized[0].id == sample_signal.id

    def test_mark_signals_synthesized(self, store: Store, sample_signal: Signal) -> None:
        store.insert_signal(sample_signal)
        store.mark_signals_synthesized([sample_signal.id])
        assert store.get_unsynthesized_signals() == []

    def test_mark_signals_synthesized_empty_list_is_noop(self, store: Store, sample_signal: Signal) -> None:
        store.insert_signal(sample_signal)
        store.mark_signals_synthesized([])
        assert len(store.get_unsynthesized_signals()) == 1

    def test_mark_partial_synthesized(self, store: Store) -> None:
        s1 = _make_signal(sig_id="sig-syn-1", url="https://a.com/1")
        s2 = _make_signal(sig_id="sig-syn-2", url="https://a.com/2")
        store.insert_signal(s1)
        store.insert_signal(s2)
        store.mark_signals_synthesized(["sig-syn-1"])
        unsynthesized = store.get_unsynthesized_signals()
        assert len(unsynthesized) == 1
        assert unsynthesized[0].id == "sig-syn-2"

    def test_unsynthesized_respects_limit(self, store: Store) -> None:
        for i in range(5):
            store.insert_signal(_make_signal(sig_id=f"sig-u-{i}", url=f"https://a.com/u-{i}"))
        assert len(store.get_unsynthesized_signals(limit=2)) == 2


class TestSignalRoles:
    def test_update_signal_role(self, store: Store, sample_signal: Signal) -> None:
        store.insert_signal(sample_signal)
        store.update_signal_role(sample_signal.id, "problem")
        sig = store.get_signal(sample_signal.id)
        assert sig is not None
        assert sig.metadata.get("signal_role") == "problem"

    def test_get_signals_by_role(self, store: Store) -> None:
        s1 = _make_signal(sig_id="sig-role-1", url="https://a.com/r1", metadata={"signal_role": "problem"})
        s2 = _make_signal(sig_id="sig-role-2", url="https://a.com/r2", metadata={"signal_role": "solution"})
        s3 = _make_signal(sig_id="sig-role-3", url="https://a.com/r3", metadata={"signal_role": "problem"})
        store.insert_signal(s1)
        store.insert_signal(s2)
        store.insert_signal(s3)
        # signal_role column is set from metadata["signal_role"] on insert
        problems = store.get_signals_by_role("problem")
        assert len(problems) == 2
        solutions = store.get_signals_by_role("solution")
        assert len(solutions) == 1

    def test_get_signals_by_role_empty(self, store: Store, sample_signal: Signal) -> None:
        store.insert_signal(sample_signal)
        assert store.get_signals_by_role("nonexistent") == []

    def test_get_signals_by_role_respects_limit(self, store: Store) -> None:
        for i in range(5):
            store.insert_signal(
                _make_signal(
                    sig_id=f"sig-rl-{i}",
                    url=f"https://a.com/rl-{i}",
                    metadata={"signal_role": "market"},
                )
            )
        assert len(store.get_signals_by_role("market", limit=3)) == 3


# ── Insight operations ───────────────────────────────────────────────


class TestInsightOperations:
    def test_insert_insight_auto_generates_id(self, store: Store) -> None:
        ins = Insight(
            category=InsightCategory.GAP,
            title="Auto ID insight",
            summary="Summary",
            evidence=["sig-1"],
            confidence=0.8,
            domains=["testing"],
            implications=["implication"],
            time_horizon="near_term",
        )
        stored = store.insert_insight(ins)
        assert stored.id.startswith("ins-")

    def test_get_insights_empty(self, store: Store) -> None:
        assert store.get_insights() == []

    def test_get_insights_respects_limit(self, store: Store) -> None:
        for i in range(5):
            ins = Insight(
                id=f"ins-lim-{i}",
                category=InsightCategory.GAP,
                title=f"Insight {i}",
                summary="Summary",
                evidence=[],
                confidence=0.5,
                domains=[],
                implications=[],
                time_horizon="near_term",
            )
            store.insert_insight(ins)
        assert len(store.get_insights(limit=3)) == 3

    def test_get_insight_not_found(self, store: Store) -> None:
        assert store.get_insight("ins-nonexistent") is None

    def test_insight_roundtrip_fields(self, store: Store, sample_insight: Insight) -> None:
        store.insert_insight(sample_insight)
        retrieved = store.get_insight(sample_insight.id)
        assert retrieved is not None
        assert retrieved.category == InsightCategory.GAP
        assert retrieved.confidence == 0.8
        assert retrieved.domains == ["mcp", "testing"]
        assert retrieved.implications == ["Testing framework opportunity", "Quality gap in ecosystem"]
        assert retrieved.time_horizon == "near_term"


# ── BuildableUnit operations ─────────────────────────────────────────


class TestBuildableUnitOperations:
    def test_insert_unit_auto_generates_id(self, store: Store) -> None:
        unit = BuildableUnit(
            title="Auto ID unit",
            one_liner="Test",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="problem",
            solution="solution",
            value_proposition="value",
        )
        stored = store.insert_buildable_unit(unit)
        assert stored.id.startswith("bu-")

    def test_get_buildable_unit_not_found(self, store: Store) -> None:
        assert store.get_buildable_unit("bu-nonexistent") is None

    def test_get_buildable_units_empty(self, store: Store) -> None:
        assert store.get_buildable_units() == []

    def test_get_buildable_units_status_filter(self, store: Store) -> None:
        u1 = _make_unit("bu-draft")
        u2 = _make_unit("bu-eval")
        store.insert_buildable_unit(u1)
        store.insert_buildable_unit(u2)
        store.update_buildable_unit_status("bu-eval", "evaluated")

        drafts = store.get_buildable_units(status="draft")
        assert len(drafts) == 1
        assert drafts[0].id == "bu-draft"

        evaluated = store.get_buildable_units(status="evaluated")
        assert len(evaluated) == 1
        assert evaluated[0].id == "bu-eval"

    def test_get_buildable_units_respects_limit(self, store: Store) -> None:
        for i in range(5):
            store.insert_buildable_unit(_make_unit(f"bu-lim-{i}"))
        assert len(store.get_buildable_units(limit=3)) == 3

    def test_update_buildable_unit_status_updates_timestamp(self, store: Store, sample_unit: BuildableUnit) -> None:
        store.insert_buildable_unit(sample_unit)
        original = store.get_buildable_unit(sample_unit.id)
        store.update_buildable_unit_status(sample_unit.id, "evaluated")
        updated = store.get_buildable_unit(sample_unit.id)
        assert updated.status == "evaluated"
        # updated_at should be at least as recent as original
        assert updated.updated_at >= original.updated_at

    def test_buildable_unit_roundtrip_fields(self, store: Store, sample_unit: BuildableUnit) -> None:
        store.insert_buildable_unit(sample_unit)
        unit = store.get_buildable_unit(sample_unit.id)
        assert unit is not None
        assert unit.one_liner == "Standardized testing for MCP servers"
        assert unit.ideation_mode == IdeationMode.DIRECT
        assert unit.tech_approach == "TypeScript CLI with protocol-level validation"
        assert unit.suggested_stack == {"language": "typescript", "runtime": "node"}
        assert unit.composability_notes == "Integrates with CI/CD pipelines"
        assert unit.evidence_signals == ["sig-test001"]


# ── Evaluation operations ────────────────────────────────────────────


class TestEvaluationOperations:
    def test_get_evaluation_not_found(self, store: Store) -> None:
        assert store.get_evaluation("bu-nonexistent") is None

    def test_evaluation_roundtrip_all_dimensions(
        self, store: Store, sample_unit: BuildableUnit, sample_evaluation: UtilityEvaluation
    ) -> None:
        store.insert_buildable_unit(sample_unit)
        store.insert_evaluation(sample_evaluation)
        ev = store.get_evaluation(sample_unit.id)
        assert ev is not None
        assert ev.pain_severity.value == 8.0
        assert ev.addressable_scale.value == 7.0
        assert ev.build_effort.value == 7.5
        assert ev.composability.value == 8.5
        assert ev.competitive_density.value == 9.0
        assert ev.timing_fit.value == 8.0
        assert ev.compounding_value.value == 7.0
        assert ev.strengths == ["High demand", "Low competition"]
        assert ev.weaknesses == ["Niche audience"]
        assert ev.weights_used["pain_severity"] == 0.20

    def test_evaluation_upsert_replaces(
        self, store: Store, sample_unit: BuildableUnit, sample_evaluation: UtilityEvaluation
    ) -> None:
        store.insert_buildable_unit(sample_unit)
        store.insert_evaluation(sample_evaluation)

        updated = _make_evaluation(sample_unit.id, overall_score=90.0)
        store.insert_evaluation(updated)

        ev = store.get_evaluation(sample_unit.id)
        assert ev.overall_score == 90.0


# ── TactSpec operations ──────────────────────────────────────────────


class TestTactSpecOperations:
    def test_get_tact_spec_not_found(self, store: Store) -> None:
        assert store.get_tact_spec("bu-nonexistent") is None

    def test_tact_spec_roundtrip(
        self, store: Store, sample_unit: BuildableUnit, sample_tact_spec: TactSpec
    ) -> None:
        store.insert_buildable_unit(sample_unit)
        store.insert_tact_spec(sample_tact_spec)
        spec = store.get_tact_spec(sample_unit.id)
        assert spec is not None
        assert spec.buildable_unit_id == sample_unit.id
        assert spec.product.name == "mcp-test-framework"
        assert spec.architecture.invariants == ["All tests must be deterministic"]
        assert len(spec.requirements) == 1

    def test_tact_spec_upsert_replaces(
        self, store: Store, sample_unit: BuildableUnit, sample_tact_spec: TactSpec
    ) -> None:
        store.insert_buildable_unit(sample_unit)
        store.insert_tact_spec(sample_tact_spec)

        # Modify and re-insert
        sample_tact_spec.product.vision = "Updated vision"
        store.insert_tact_spec(sample_tact_spec)

        spec = store.get_tact_spec(sample_unit.id)
        assert spec.product.vision == "Updated vision"


# ── Feedback operations ──────────────────────────────────────────────


class TestFeedbackOperations:
    def test_insert_feedback_without_evaluation(self, store: Store) -> None:
        """Feedback can be inserted even when no evaluation exists."""
        store.insert_buildable_unit(_make_unit("bu-fb-1"))
        store.insert_feedback("bu-fb-1", "approved", "looks good")
        # Should not raise; dimension_values will be empty
        outcomes = store.get_feedback_outcomes()
        assert len(outcomes) == 1
        assert outcomes[0]["success"] is True
        assert outcomes[0]["dimension_values"] == {}

    def test_insert_feedback_with_evaluation_captures_dimensions(self, store: Store) -> None:
        store.insert_buildable_unit(_make_unit("bu-fb-2"))
        store.insert_evaluation(_make_evaluation("bu-fb-2"))
        store.insert_feedback("bu-fb-2", "rejected", "too niche")

        outcomes = store.get_feedback_outcomes()
        assert len(outcomes) == 1
        assert outcomes[0]["success"] is False
        assert outcomes[0]["dimension_values"]["pain_severity"] == 8.0

    def test_feedback_outcomes_approved_and_published_are_success(self, store: Store) -> None:
        store.insert_buildable_unit(_make_unit("bu-fb-3"))
        store.insert_buildable_unit(_make_unit("bu-fb-4"))
        store.insert_buildable_unit(_make_unit("bu-fb-5"))
        store.insert_buildable_unit(_make_unit("bu-fb-6"))

        store.insert_feedback("bu-fb-3", "approved")
        store.insert_feedback("bu-fb-4", "published")
        store.insert_feedback("bu-fb-5", "rejected")
        store.insert_feedback("bu-fb-6", "abandoned")

        outcomes = store.get_feedback_outcomes()
        success_map = {o["buildable_unit_id"]: o["success"] for o in outcomes}
        assert success_map["bu-fb-3"] is True
        assert success_map["bu-fb-4"] is True
        assert success_map["bu-fb-5"] is False
        assert success_map["bu-fb-6"] is False

    def test_get_feedback_outcomes_empty(self, store: Store) -> None:
        assert store.get_feedback_outcomes() == []


# ── Analytics: get_adapter_quality_stats ──────────────────────────────


class TestAdapterQualityStats:
    def test_empty_database(self, store: Store) -> None:
        stats = store.get_adapter_quality_stats()
        assert stats == {}

    def test_signals_only_no_insights_or_units(self, store: Store) -> None:
        store.insert_signal(_make_signal(adapter="hn", sig_id="sig-qs-1", url="https://a.com/qs1"))
        store.insert_signal(_make_signal(adapter="hn", sig_id="sig-qs-2", url="https://a.com/qs2"))
        stats = store.get_adapter_quality_stats()
        assert stats["hn"]["total_signals"] == 2
        assert stats["hn"]["insight_hit_rate"] == 0.0
        assert stats["hn"]["idea_hit_rate"] == 0.0

    def test_insight_hit_rate_calculation(self, store: Store) -> None:
        """1 of 2 signals referenced in an insight → 50% hit rate."""
        s1 = _make_signal(adapter="reddit", sig_id="sig-ihr-1", url="https://a.com/ihr1")
        s2 = _make_signal(adapter="reddit", sig_id="sig-ihr-2", url="https://a.com/ihr2")
        store.insert_signal(s1)
        store.insert_signal(s2)

        ins = Insight(
            id="ins-ihr-1",
            category=InsightCategory.GAP,
            title="Test",
            summary="Test",
            evidence=["sig-ihr-1"],  # only references s1
            confidence=0.5,
            domains=[],
            implications=[],
            time_horizon="near_term",
        )
        store.insert_insight(ins)

        stats = store.get_adapter_quality_stats()
        assert stats["reddit"]["total_signals"] == 2
        assert stats["reddit"]["insight_hit_rate"] == 0.5
        assert stats["reddit"]["idea_hit_rate"] == 0.0

    def test_idea_hit_rate_calculation(self, store: Store) -> None:
        """1 of 3 signals referenced in a buildable unit → ~33% hit rate."""
        for i in range(3):
            store.insert_signal(_make_signal(adapter="npm", sig_id=f"sig-idhr-{i}", url=f"https://a.com/idhr{i}"))

        unit = _make_unit("bu-idhr-1", evidence_signals=["sig-idhr-0"])
        store.insert_buildable_unit(unit)

        stats = store.get_adapter_quality_stats()
        assert stats["npm"]["total_signals"] == 3
        assert stats["npm"]["idea_hit_rate"] == pytest.approx(1 / 3)

    def test_multi_adapter_stats(self, store: Store) -> None:
        """Multiple adapters produce independent stats."""
        store.insert_signal(_make_signal(adapter="hn", sig_id="sig-ma-1", url="https://a.com/ma1"))
        store.insert_signal(_make_signal(adapter="reddit", sig_id="sig-ma-2", url="https://a.com/ma2"))

        ins = Insight(
            id="ins-ma-1",
            category=InsightCategory.GAP,
            title="Test",
            summary="Test",
            evidence=["sig-ma-1"],
            confidence=0.5,
            domains=[],
            implications=[],
            time_horizon="near_term",
        )
        store.insert_insight(ins)

        stats = store.get_adapter_quality_stats()
        assert stats["hn"]["insight_hit_rate"] == 1.0
        assert stats["reddit"]["insight_hit_rate"] == 0.0

    def test_both_hit_rates_combined(self, store: Store) -> None:
        """A signal referenced by both insight and unit counts in both rates."""
        store.insert_signal(_make_signal(adapter="gh", sig_id="sig-both-1", url="https://a.com/b1"))

        ins = Insight(
            id="ins-both-1",
            category=InsightCategory.GAP,
            title="Test",
            summary="Test",
            evidence=["sig-both-1"],
            confidence=0.5,
            domains=[],
            implications=[],
            time_horizon="near_term",
        )
        store.insert_insight(ins)

        unit = _make_unit("bu-both-1", evidence_signals=["sig-both-1"])
        store.insert_buildable_unit(unit)

        stats = store.get_adapter_quality_stats()
        assert stats["gh"]["insight_hit_rate"] == 1.0
        assert stats["gh"]["idea_hit_rate"] == 1.0


# ── Analytics: get_adapter_approval_stats ─────────────────────────────


class TestAdapterApprovalStats:
    def test_empty_database(self, store: Store) -> None:
        assert store.get_adapter_approval_stats() == {}

    def test_single_approved(self, store: Store) -> None:
        sig = _make_signal(adapter="hn", sig_id="sig-as-1")
        store.insert_signal(sig)
        unit = _make_unit("bu-as-1", evidence_signals=["sig-as-1"])
        store.insert_buildable_unit(unit)
        store.insert_feedback("bu-as-1", "approved")

        stats = store.get_adapter_approval_stats()
        assert stats["hn"]["approved"] == 1
        assert stats["hn"]["rejected"] == 0
        assert stats["hn"]["approval_rate"] == 1.0

    def test_mixed_outcomes(self, store: Store) -> None:
        for i in range(3):
            store.insert_signal(_make_signal(adapter="hn", sig_id=f"sig-mx-{i}", url=f"https://a.com/mx{i}"))
            unit = _make_unit(f"bu-mx-{i}", evidence_signals=[f"sig-mx-{i}"])
            store.insert_buildable_unit(unit)

        store.insert_feedback("bu-mx-0", "approved")
        store.insert_feedback("bu-mx-1", "rejected")
        store.insert_feedback("bu-mx-2", "published")

        stats = store.get_adapter_approval_stats()
        assert stats["hn"]["approved"] == 2  # approved + published
        assert stats["hn"]["rejected"] == 1
        assert stats["hn"]["approval_rate"] == pytest.approx(2 / 3)


# ── Analytics: get_feedback_with_attribution ──────────────────────────


class TestFeedbackWithAttribution:
    def test_empty(self, store: Store) -> None:
        assert store.get_feedback_with_attribution() == []

    def test_traces_signals_to_adapters(self, store: Store) -> None:
        sig = _make_signal(adapter="reddit", sig_id="sig-fwa-1")
        store.insert_signal(sig)
        unit = _make_unit("bu-fwa-1", evidence_signals=["sig-fwa-1"])
        store.insert_buildable_unit(unit)
        store.insert_evaluation(_make_evaluation("bu-fwa-1", overall_score=80.0))
        store.insert_feedback("bu-fwa-1", "approved", "great idea")

        results = store.get_feedback_with_attribution()
        assert len(results) == 1
        r = results[0]
        assert r["unit_id"] == "bu-fwa-1"
        assert r["outcome"] == "approved"
        assert r["reason"] == "great idea"
        assert "reddit" in r["source_adapters"]
        assert r["eval_score"] == 80.0

    def test_no_evaluation_defaults_score_to_zero(self, store: Store) -> None:
        sig = _make_signal(adapter="hn", sig_id="sig-fwa-2")
        store.insert_signal(sig)
        unit = _make_unit("bu-fwa-2", evidence_signals=["sig-fwa-2"])
        store.insert_buildable_unit(unit)
        store.insert_feedback("bu-fwa-2", "rejected")

        results = store.get_feedback_with_attribution()
        assert results[0]["eval_score"] == 0.0


# ── Pipeline runs ────────────────────────────────────────────────────


class TestPipelineRuns:
    def test_insert_and_get(self, store: Store) -> None:
        store.insert_pipeline_run("run-test-1", {"profile": "default"})
        runs = store.get_pipeline_runs()
        assert len(runs) == 1
        assert runs[0]["id"] == "run-test-1"
        assert runs[0]["config"] == {"profile": "default"}
        assert runs[0]["completed_at"] is None

    def test_update_pipeline_run(self, store: Store) -> None:
        store.insert_pipeline_run("run-test-2", {})
        store.update_pipeline_run("run-test-2", signals_fetched=10, signals_new=5)
        runs = store.get_pipeline_runs()
        assert runs[0]["completed_at"] is not None
        assert runs[0]["signals_fetched"] == 10
        assert runs[0]["signals_new"] == 5

    def test_get_pipeline_runs_empty(self, store: Store) -> None:
        assert store.get_pipeline_runs() == []

    def test_pipeline_runs_ordered_by_recency(self, store: Store) -> None:
        store.insert_pipeline_run("run-old", {"order": 1})
        store.insert_pipeline_run("run-new", {"order": 2})
        runs = store.get_pipeline_runs()
        assert runs[0]["id"] == "run-new"

    def test_pipeline_runs_limit(self, store: Store) -> None:
        for i in range(5):
            store.insert_pipeline_run(f"run-lim-{i}", {})
        assert len(store.get_pipeline_runs(limit=3)) == 3


# ── Edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    def test_wal_mode_initialization(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "wal_test.db")
        s = Store(db_path=db_path, wal_mode=True)
        result = s.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert result == "wal"
        s.close()

    def test_default_journal_mode_is_not_wal(self, store: Store) -> None:
        result = store.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert result != "wal"

    def test_empty_db_all_queries_return_empty(self, store: Store) -> None:
        assert store.get_signals() == []
        assert store.get_insights() == []
        assert store.get_buildable_units() == []
        assert store.get_unsynthesized_signals() == []
        assert store.get_feedback_outcomes() == []
        assert store.get_pipeline_runs() == []
        assert store.count_signals() == 0
        assert store.get_adapter_quality_stats() == {}
        assert store.get_adapter_approval_stats() == {}
        assert store.get_feedback_with_attribution() == []

    def test_close_and_reopen(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "reopen.db")
        s = Store(db_path=db_path)
        sig = _make_signal(sig_id="sig-persist")
        s.insert_signal(sig)
        s.close()

        s2 = Store(db_path=db_path)
        assert s2.get_signal("sig-persist") is not None
        s2.close()

    def test_signal_metadata_roundtrip(self, store: Store) -> None:
        sig = _make_signal(
            sig_id="sig-meta",
            metadata={"signal_role": "problem", "custom_key": "custom_value"},
        )
        store.insert_signal(sig)
        retrieved = store.get_signal("sig-meta")
        assert retrieved is not None
        assert retrieved.metadata["custom_key"] == "custom_value"
        assert retrieved.metadata["signal_role"] == "problem"
