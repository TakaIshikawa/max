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

    def test_get_signal_by_url(self, store: Store) -> None:
        sig = _make_signal(sig_id="sig-url", url="https://example.com/by-url")
        store.insert_signal(sig)

        found = store.get_signal_by_url("https://example.com/by-url")

        assert found is not None
        assert found.id == "sig-url"
        assert store.get_signal_by_url("https://example.com/missing") is None

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

    def test_archive_signal_hides_from_lists_and_counts_but_preserves_direct_lookup(self, store: Store) -> None:
        active = _make_signal(sig_id="sig-active", url="https://a.com/active")
        archived = _make_signal(sig_id="sig-archived", url="https://a.com/archived")
        store.insert_signal(active)
        store.insert_signal(archived)

        assert store.archive_signal(archived.id) is True

        assert [sig.id for sig in store.get_signals(limit=100)] == [active.id]
        assert store.count_signals() == 1
        direct = store.get_signal(archived.id)
        assert direct is not None
        assert direct.id == archived.id

    def test_restore_signal_returns_archived_signal_to_lists_and_counts(self, store: Store) -> None:
        signal = _make_signal(sig_id="sig-restore", url="https://a.com/restore")
        store.insert_signal(signal)
        store.archive_signal(signal.id)
        assert store.count_signals() == 0

        assert store.restore_signal(signal.id) is True

        assert store.count_signals() == 1
        assert [sig.id for sig in store.get_signals(limit=100)] == [signal.id]

    def test_archive_and_restore_signal_return_false_for_missing_signal(self, store: Store) -> None:
        assert store.archive_signal("sig-missing") is False
        assert store.restore_signal("sig-missing") is False


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
        assert unit.specific_user == "MCP server maintainer"
        assert unit.buyer == "developer platform lead"
        assert unit.workflow_context == "pre-release CI validation"
        assert unit.current_workaround == "manual protocol testing"
        assert unit.why_now == "MCP server adoption is growing"
        assert unit.validation_plan == "run against five open-source MCP servers"
        assert unit.first_10_customers == "teams publishing MCP servers"
        assert unit.domain_risks == ["protocol churn"]
        assert unit.evidence_rationale == "Insight shows lack of standardized testing."
        assert unit.novelty_score == 7.0
        assert unit.usefulness_score == 8.0
        assert unit.quality_score == 7.5
        assert unit.rejection_tags == []


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
        assert runs[0]["status"] == "running"
        assert runs[0]["error_message"] == ""

    def test_update_pipeline_run(self, store: Store) -> None:
        store.insert_pipeline_run("run-test-2", {})
        store.update_pipeline_run("run-test-2", signals_fetched=10, signals_new=5)
        runs = store.get_pipeline_runs()
        assert runs[0]["completed_at"] is not None
        assert runs[0]["signals_fetched"] == 10
        assert runs[0]["signals_new"] == 5
        assert runs[0]["status"] == "completed"

    def test_update_pipeline_run_failed_status(self, store: Store) -> None:
        store.insert_pipeline_run("run-test-failed", {})
        store.update_pipeline_run(
            "run-test-failed",
            status="failed",
            error_message="ValidationError: ideas missing",
        )
        runs = store.get_pipeline_runs()
        assert runs[0]["status"] == "failed"
        assert runs[0]["error_message"] == "ValidationError: ideas missing"

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


# ── Schema and Migrations ────────────────────────────────────────────


class TestSchemaAndMigrations:
    def test_fresh_db_has_correct_schema_version(self, tmp_path: Path) -> None:
        """Fresh database should have the current schema version."""
        from max.store.migrations import SCHEMA_VERSION

        db_path = str(tmp_path / "fresh.db")
        s = Store(db_path=db_path)
        version = s.get_schema_version()
        assert version == SCHEMA_VERSION
        s.close()

    def test_idempotent_migration_runs(self, tmp_path: Path) -> None:
        """Running ensure_schema multiple times should not fail."""
        from max.store.migrations import ensure_schema

        db_path = str(tmp_path / "idempotent.db")
        s = Store(db_path=db_path)

        # Run ensure_schema again manually
        ensure_schema(s.conn)
        ensure_schema(s.conn)

        # Should still work and schema version should be correct
        version = s.get_schema_version()
        from max.store.migrations import SCHEMA_VERSION
        assert version == SCHEMA_VERSION
        s.close()

    def test_all_tables_created(self, store: Store) -> None:
        """Verify all expected tables exist in the schema."""
        expected_tables = {
            "schema_version",
            "signals",
            "insights",
            "buildable_units",
            "evaluations",
            "feedback",
            "pipeline_runs",
            "pipeline_run_domains",
            "prior_art_matches",
            "idea_critiques",
            "idea_memory",
            "design_briefs",
            "design_brief_sources",
            "domain_quality_scores",
            "domain_quality_memory",
            "domain_quality_eval_runs",
            "domain_quality_eval_items",
            "embeddings",
        }

        cursor = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        actual_tables = {row[0] for row in cursor.fetchall()}

        assert expected_tables.issubset(actual_tables)

    def test_required_indexes_created(self, store: Store) -> None:
        """Verify required indexes exist."""
        cursor = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = {row[0] for row in cursor.fetchall()}

        # Key indexes from schema
        expected = {
            "idx_signals_url",
            "idx_prd_run_id",
            "idx_prd_domain",
            "idx_prior_art_bu_id",
            "idx_signals_archived_at",
            "idx_insights_archived_at",
            "idx_pipeline_runs_archived_at",
            "idx_design_briefs_domain",
            "idx_design_briefs_status",
            "idx_design_brief_sources_idea",
            "idx_domain_quality_scores_unit",
            "idx_domain_quality_scores_domain",
            "idx_domain_quality_memory_domain",
            "idx_domain_quality_memory_outcome",
            "idx_domain_quality_eval_items_run",
            "idx_domain_quality_eval_items_idea",
        }

        assert expected.issubset(indexes)


# ── Domain Quality ──────────────────────────────────────────────────


class TestDomainQualityStore:
    def test_insert_and_get_domain_quality_score(self, store: Store) -> None:
        from max.quality.scorer import DomainQualityScore

        unit = _make_unit(unit_id="bu-dq-1")
        store.insert_buildable_unit(unit)
        score = DomainQualityScore(
            buildable_unit_id="bu-dq-1",
            domain="developer-tools",
            profile_name="devtools",
            rubric_version="v1",
            dimensions={"buyer_clarity": 8.0},
            overall_score=78.0,
            passed_gate=True,
            rejection_tags=[],
            reasoning="Good domain fit.",
        )

        score_id = store.insert_domain_quality_score(score)
        rows = store.get_domain_quality_scores("bu-dq-1")

        assert rows[0]["id"] == score_id
        assert rows[0]["dimensions"] == {"buyer_clarity": 8.0}
        assert rows[0]["passed_gate"] is True

    def test_insert_feedback_writes_domain_quality_memory(self, store: Store) -> None:
        unit = _make_unit(unit_id="bu-dqm-1")
        unit.domain = "developer-tools"
        unit.rejection_tags = ["missing_buyer"]
        store.insert_buildable_unit(unit)

        store.insert_feedback("bu-dqm-1", "rejected", "unclear buyer")
        rows = store.get_domain_quality_memory(domain="developer-tools", outcome="rejected")

        assert len(rows) == 1
        assert rows[0]["source_idea_id"] == "bu-dqm-1"
        assert rows[0]["tags"] == ["missing_buyer"]

    def test_insert_and_get_domain_quality_eval_run(self, store: Store) -> None:
        unit = _make_unit(unit_id="bu-dqe-1")
        store.insert_buildable_unit(unit)
        evaluation = _make_evaluation(unit_id="bu-dqe-1", overall_score=81.0)
        store.insert_evaluation(evaluation)

        eval_run_id = store.insert_domain_quality_eval_run(
            profile_name="devtools",
            domain="developer-tools",
            rubric_version="v1",
            baseline_pipeline_run_id="run-baseline",
            rubric_pipeline_run_id="run-rubric",
            baseline_ideas=1,
            rubric_ideas=1,
            started_at="2026-04-22T00:00:00+00:00",
            completed_at="2026-04-22T00:01:00+00:00",
            notes="smoke",
        )
        item_id = store.insert_domain_quality_eval_item(
            eval_run_id=eval_run_id,
            buildable_unit_id="bu-dqe-1",
            cohort="rubric",
            domain_quality_score=74.0,
            passed_gate=True,
            evaluation_score=81.0,
            review_outcome="approved",
            approval_score=4,
        )

        row = store.get_domain_quality_eval_run(eval_run_id)

        assert row is not None
        assert row["id"] == eval_run_id
        assert row["profile_name"] == "devtools"
        assert row["baseline_pipeline_run_id"] == "run-baseline"
        assert row["rubric_pipeline_run_id"] == "run-rubric"
        assert row["notes"] == "smoke"
        assert row["items"][0]["id"] == item_id
        assert row["items"][0]["cohort"] == "rubric"
        assert row["items"][0]["domain_quality_score"] == 74.0
        assert row["items"][0]["passed_gate"] is True
        assert row["items"][0]["evaluation_score"] == 81.0
        assert row["items"][0]["review_outcome"] == "approved"
        assert row["items"][0]["approval_score"] == 4


# ── Cursor Encoding/Decoding ─────────────────────────────────────────


class TestCursorEncoding:
    def test_encode_decode_roundtrip(self) -> None:
        """Encode then decode should return original values."""
        from max.store.db import _encode_cursor, _decode_cursor

        timestamp = "2026-01-15T10:30:00.000000+00:00"
        entity_id = "sig-test123"

        cursor = _encode_cursor(timestamp, entity_id)
        decoded_timestamp, decoded_id = _decode_cursor(cursor)

        assert decoded_timestamp == timestamp
        assert decoded_id == entity_id

    def test_decode_invalid_base64_raises_value_error(self) -> None:
        """Decode with invalid base64 should raise ValueError."""
        from max.store.db import _decode_cursor

        with pytest.raises(ValueError, match="Invalid cursor format"):
            _decode_cursor("not-valid-base64!!!")

    def test_decode_missing_separator_raises_value_error(self) -> None:
        """Decode with valid base64 but missing pipe separator should raise ValueError."""
        import base64
        from max.store.db import _decode_cursor

        # Create valid base64 but without pipe separator
        invalid_data = "no_separator_here"
        invalid_cursor = base64.b64encode(invalid_data.encode()).decode()

        with pytest.raises(ValueError, match="Invalid cursor format"):
            _decode_cursor(invalid_cursor)

    def test_encode_with_special_characters_in_entity_id(self) -> None:
        """Encode should handle special characters in entity_id."""
        from max.store.db import _encode_cursor, _decode_cursor

        timestamp = "2026-01-15T10:30:00.000000+00:00"
        # Entity ID with special characters
        entity_id = "sig-test|with|pipes|and-dashes_underscores"

        cursor = _encode_cursor(timestamp, entity_id)
        decoded_timestamp, decoded_id = _decode_cursor(cursor)

        # Should split on first pipe only
        assert decoded_timestamp == timestamp
        assert decoded_id == entity_id


# ── Signals Pagination ───────────────────────────────────────────────


class TestSignalsPagination:
    def test_empty_store_returns_empty_list_and_no_cursor(self, store: Store) -> None:
        """Empty store should return empty list and None cursor."""
        signals, next_cursor = store.get_signals_paginated()
        assert signals == []
        assert next_cursor is None

    def test_fewer_signals_than_limit_returns_all_no_cursor(self, store: Store) -> None:
        """Fewer signals than limit should return all signals and next_cursor=None."""
        for i in range(3):
            store.insert_signal(_make_signal(sig_id=f"sig-pag-{i}", url=f"https://a.com/pag{i}"))

        signals, next_cursor = store.get_signals_paginated(limit=10)
        assert len(signals) == 3
        assert next_cursor is None

    def test_more_signals_than_limit_returns_exactly_limit_and_cursor(self, store: Store) -> None:
        """More signals than limit should return exactly limit signals and a non-None next_cursor."""
        for i in range(10):
            store.insert_signal(_make_signal(sig_id=f"sig-pag2-{i}", url=f"https://a.com/pag2-{i}"))

        signals, next_cursor = store.get_signals_paginated(limit=5)
        assert len(signals) == 5
        assert next_cursor is not None

    def test_using_next_cursor_returns_next_page(self, store: Store) -> None:
        """Using next_cursor from first page should return the next page."""
        for i in range(10):
            store.insert_signal(_make_signal(sig_id=f"sig-pag3-{i}", url=f"https://a.com/pag3-{i}"))

        # Get first page
        page1, cursor1 = store.get_signals_paginated(limit=5)
        assert len(page1) == 5
        assert cursor1 is not None

        # Get second page using cursor
        page2, cursor2 = store.get_signals_paginated(cursor=cursor1, limit=5)
        assert len(page2) == 5
        assert cursor2 is None  # No more pages

        # Verify no overlap between pages
        page1_ids = {s.id for s in page1}
        page2_ids = {s.id for s in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_full_pagination_walk(self, store: Store) -> None:
        """Full pagination walk through all signals should return all unique signals."""
        n_signals = 25
        for i in range(n_signals):
            store.insert_signal(_make_signal(sig_id=f"sig-walk-{i}", url=f"https://a.com/walk-{i}"))

        all_signals = []
        cursor = None
        page_limit = 7

        while True:
            signals, cursor = store.get_signals_paginated(cursor=cursor, limit=page_limit)
            all_signals.extend(signals)
            if cursor is None:
                break

        # Verify we got all signals exactly once
        assert len(all_signals) == n_signals
        all_ids = [s.id for s in all_signals]
        assert len(set(all_ids)) == n_signals  # All unique

    def test_pagination_with_source_type_filter(self, store: Store) -> None:
        """Pagination with source_type filter should only return filtered signals."""
        # Insert mixed source types
        for i in range(5):
            store.insert_signal(
                _make_signal(
                    adapter="hn",
                    sig_id=f"sig-forum-{i}",
                    url=f"https://a.com/forum-{i}",
                    source_type=SignalSourceType.FORUM,
                )
            )
        for i in range(3):
            store.insert_signal(
                _make_signal(
                    adapter="npm",
                    sig_id=f"sig-reg-{i}",
                    url=f"https://a.com/reg-{i}",
                    source_type=SignalSourceType.REGISTRY,
                )
            )

        signals, next_cursor = store.get_signals_paginated(source_type="forum", limit=10)
        assert len(signals) == 5
        assert all(s.source_type == SignalSourceType.FORUM for s in signals)

        signals, next_cursor = store.get_signals_paginated(source_type="registry", limit=10)
        assert len(signals) == 3
        assert all(s.source_type == SignalSourceType.REGISTRY for s in signals)

    def test_pagination_with_signal_role_filter(self, store: Store) -> None:
        """Pagination with signal_role filter should only return filtered signals."""
        for i in range(4):
            store.insert_signal(
                _make_signal(
                    sig_id=f"sig-problem-{i}",
                    url=f"https://a.com/problem-{i}",
                    metadata={"signal_role": "problem"},
                )
            )
        for i in range(2):
            store.insert_signal(
                _make_signal(
                    sig_id=f"sig-solution-{i}",
                    url=f"https://a.com/solution-{i}",
                    metadata={"signal_role": "solution"},
                )
            )

        signals, next_cursor = store.get_signals_paginated(signal_role="problem", limit=10)

        assert len(signals) == 4
        assert next_cursor is None
        assert all(s.signal_role == "problem" for s in signals)

    def test_pagination_with_source_adapter_filter(self, store: Store) -> None:
        """Pagination with source_adapter filter should only return filtered signals."""
        for i in range(3):
            store.insert_signal(
                _make_signal(
                    adapter="hackernews",
                    sig_id=f"sig-hn-{i}",
                    url=f"https://a.com/hn-{i}",
                )
            )
        for i in range(2):
            store.insert_signal(
                _make_signal(
                    adapter="reddit",
                    sig_id=f"sig-reddit-{i}",
                    url=f"https://a.com/reddit-{i}",
                )
            )

        signals, next_cursor = store.get_signals_paginated(
            source_adapter="hackernews", limit=10
        )

        assert len(signals) == 3
        assert next_cursor is None
        assert all(s.source_adapter == "hackernews" for s in signals)

    def test_pagination_with_source_type_and_signal_role_filter(self, store: Store) -> None:
        """Pagination should combine source_type, source_adapter, and signal_role filters."""
        store.insert_signal(
            _make_signal(
                sig_id="sig-forum-problem",
                url="https://a.com/forum-problem",
                adapter="hackernews",
                source_type=SignalSourceType.FORUM,
                metadata={"signal_role": "problem"},
            )
        )
        store.insert_signal(
            _make_signal(
                sig_id="sig-registry-problem",
                url="https://a.com/registry-problem",
                adapter="npm",
                source_type=SignalSourceType.REGISTRY,
                metadata={"signal_role": "problem"},
            )
        )
        store.insert_signal(
            _make_signal(
                sig_id="sig-forum-solution",
                url="https://a.com/forum-solution",
                adapter="reddit",
                source_type=SignalSourceType.FORUM,
                metadata={"signal_role": "solution"},
            )
        )
        store.insert_signal(
            _make_signal(
                sig_id="sig-forum-problem-reddit",
                url="https://a.com/forum-problem-reddit",
                adapter="reddit",
                source_type=SignalSourceType.FORUM,
                metadata={"signal_role": "problem"},
            )
        )

        signals, next_cursor = store.get_signals_paginated(
            source_type="forum", source_adapter="hackernews", signal_role="problem", limit=10
        )

        assert next_cursor is None
        assert [s.id for s in signals] == ["sig-forum-problem"]

    def test_count_signals_with_signal_role_filter(self, store: Store) -> None:
        """Count should combine source_type, source_adapter, and signal_role filters."""
        store.insert_signal(
            _make_signal(
                sig_id="sig-count-forum-problem",
                url="https://a.com/count-forum-problem",
                adapter="hackernews",
                source_type=SignalSourceType.FORUM,
                metadata={"signal_role": "problem"},
            )
        )
        store.insert_signal(
            _make_signal(
                sig_id="sig-count-registry-problem",
                url="https://a.com/count-registry-problem",
                adapter="npm",
                source_type=SignalSourceType.REGISTRY,
                metadata={"signal_role": "problem"},
            )
        )
        store.insert_signal(
            _make_signal(
                sig_id="sig-count-forum-solution",
                url="https://a.com/count-forum-solution",
                adapter="reddit",
                source_type=SignalSourceType.FORUM,
                metadata={"signal_role": "solution"},
            )
        )
        store.insert_signal(
            _make_signal(
                sig_id="sig-count-forum-problem-reddit",
                url="https://a.com/count-forum-problem-reddit",
                adapter="reddit",
                source_type=SignalSourceType.FORUM,
                metadata={"signal_role": "problem"},
            )
        )

        assert store.count_signals(signal_role="problem") == 3
        assert store.count_signals(source_adapter="reddit") == 2
        assert (
            store.count_signals(
                source_type="forum", source_adapter="hackernews", signal_role="problem"
            )
            == 1
        )

    def test_invalid_cursor_raises_value_error(self, store: Store) -> None:
        """Invalid cursor string should raise ValueError."""
        store.insert_signal(_make_signal(sig_id="sig-ic-1", url="https://a.com/ic1"))

        with pytest.raises(ValueError, match="Invalid cursor format"):
            store.get_signals_paginated(cursor="invalid-cursor-format")


# ── Transaction Management ───────────────────────────────────────────


class TestTransactions:
    def test_transaction_commits_on_success(self, store: Store) -> None:
        """Transaction should commit changes when no exception occurs."""
        with store.transaction():
            sig = _make_signal(sig_id="sig-tx-1", url="https://a.com/tx1")
            store.insert_signal(sig)

        # Should be persisted
        assert store.get_signal("sig-tx-1") is not None

    def test_transaction_rolls_back_on_error(self, store: Store) -> None:
        """Transaction should rollback all changes when exception occurs."""
        try:
            with store.transaction():
                sig1 = _make_signal(sig_id="sig-tx-2", url="https://a.com/tx2")
                store.insert_signal(sig1)
                # Force an error
                raise ValueError("Test error")
        except ValueError:
            pass

        # Should not be persisted
        assert store.get_signal("sig-tx-2") is None

    def test_nested_transaction_context_preserves_flag(self, store: Store) -> None:
        """Nested transaction contexts should preserve the transaction flag."""
        # This tests the implementation detail that _in_transaction flag is preserved
        assert not getattr(store, "_in_transaction", False)

        with store.transaction():
            assert store._in_transaction is True
            sig = _make_signal(sig_id="sig-tx-3", url="https://a.com/tx3")
            store.insert_signal(sig)

        assert not getattr(store, "_in_transaction", False)

    def test_transaction_with_multiple_operations(self, store: Store) -> None:
        """Transaction should handle multiple operations atomically."""
        with store.transaction():
            sig = _make_signal(sig_id="sig-tx-4", url="https://a.com/tx4")
            store.insert_signal(sig)

            ins = Insight(
                id="ins-tx-1",
                category=InsightCategory.GAP,
                title="Test",
                summary="Test",
                evidence=["sig-tx-4"],
                confidence=0.5,
                domains=[],
                implications=[],
                time_horizon="near_term",
            )
            store.insert_insight(ins)

            unit = _make_unit("bu-tx-1", evidence_signals=["sig-tx-4"])
            store.insert_buildable_unit(unit)

        # All should be persisted
        assert store.get_signal("sig-tx-4") is not None
        assert store.get_insight("ins-tx-1") is not None
        assert store.get_buildable_unit("bu-tx-1") is not None

    def test_transaction_rollback_multiple_operations(self, store: Store) -> None:
        """Failed transaction should rollback all operations."""
        try:
            with store.transaction():
                sig = _make_signal(sig_id="sig-tx-5", url="https://a.com/tx5")
                store.insert_signal(sig)

                ins = Insight(
                    id="ins-tx-2",
                    category=InsightCategory.GAP,
                    title="Test",
                    summary="Test",
                    evidence=[],
                    confidence=0.5,
                    domains=[],
                    implications=[],
                    time_horizon="near_term",
                )
                store.insert_insight(ins)

                raise ValueError("Rollback test")
        except ValueError:
            pass

        # None should be persisted
        assert store.get_signal("sig-tx-5") is None
        assert store.get_insight("ins-tx-2") is None

    def test_commit_is_noop_inside_transaction(self, store: Store) -> None:
        """_commit() should be a no-op inside a transaction context."""
        # Insert a signal outside transaction first to verify normal commit works
        sig_before = _make_signal(sig_id="sig-tx-6", url="https://a.com/tx6")
        store.insert_signal(sig_before)
        assert store.get_signal("sig-tx-6") is not None

        # Now test inside transaction
        try:
            with store.transaction():
                sig = _make_signal(sig_id="sig-tx-7", url="https://a.com/tx7")
                store.insert_signal(sig)
                # At this point, _commit() was called by insert_signal but should be a no-op
                # The data should NOT be committed yet

                # Force an error to rollback
                raise ValueError("Test rollback")
        except ValueError:
            pass

        # Signal should NOT be persisted because _commit() was a no-op inside transaction
        assert store.get_signal("sig-tx-7") is None

    def test_nested_transaction_flag_behavior(self, store: Store) -> None:
        """Nested transaction flag (_in_transaction) should be restored correctly."""
        # Start with no transaction flag
        assert not getattr(store, "_in_transaction", False)

        with store.transaction():
            # Inside transaction, flag should be True
            assert store._in_transaction is True

            # Simulate a nested scenario (though we don't support true nesting)
            # The flag should be preserved
            inner_flag_state = store._in_transaction
            assert inner_flag_state is True

        # After exiting transaction, flag should be restored to False
        assert not getattr(store, "_in_transaction", False)


# ── Context Manager ──────────────────────────────────────────────────


class TestContextManager:
    def test_store_as_context_manager(self, tmp_path: Path) -> None:
        """Store should work as a context manager."""
        db_path = str(tmp_path / "ctx.db")

        with Store(db_path=db_path) as s:
            sig = _make_signal(sig_id="sig-ctx-1", url="https://a.com/ctx1")
            s.insert_signal(sig)

        # Verify data persisted and connection closed
        with Store(db_path=db_path) as s2:
            assert s2.get_signal("sig-ctx-1") is not None

    def test_context_manager_closes_on_exception(self, tmp_path: Path) -> None:
        """Store should close connection even when exception occurs."""
        db_path = str(tmp_path / "ctx_err.db")

        try:
            with Store(db_path=db_path) as s:
                sig = _make_signal(sig_id="sig-ctx-2", url="https://a.com/ctx2")
                s.insert_signal(sig)
                raise ValueError("Test error")
        except ValueError:
            pass

        # Connection should be closed, and data should be persisted
        with Store(db_path=db_path) as s2:
            assert s2.get_signal("sig-ctx-2") is not None

    def test_context_manager_doesnt_suppress_exceptions(self, tmp_path: Path) -> None:
        """Context manager should not suppress exceptions."""
        db_path = str(tmp_path / "ctx_suppress.db")

        with pytest.raises(ValueError, match="Test exception"):
            with Store(db_path=db_path):
                raise ValueError("Test exception")


# ── Prior Art Operations ─────────────────────────────────────────────


class TestPriorArtOperations:
    def test_insert_and_get_prior_art_matches(self, store: Store) -> None:
        """Insert and retrieve prior art matches."""
        store.insert_buildable_unit(_make_unit("bu-pa-1"))

        match = {
            "source": "github",
            "title": "Similar Project",
            "url": "https://github.com/user/repo",
            "description": "A similar implementation",
            "relevance_score": 0.85,
            "match_signals": {"overlap": ["feature1", "feature2"]},
            "search_query": "similar project query",
        }

        match_id = store.insert_prior_art_match("bu-pa-1", match)
        assert match_id.startswith("pa-")

        matches = store.get_prior_art_matches("bu-pa-1")
        assert len(matches) == 1
        assert matches[0]["title"] == "Similar Project"
        assert matches[0]["relevance_score"] == 0.85

    def test_get_prior_art_matches_empty(self, store: Store) -> None:
        """Get matches for unit with no prior art."""
        store.insert_buildable_unit(_make_unit("bu-pa-2"))
        assert store.get_prior_art_matches("bu-pa-2") == []

    def test_update_prior_art_status(self, store: Store) -> None:
        """Update prior art status for buildable unit."""
        store.insert_buildable_unit(_make_unit("bu-pa-3"))
        store.update_prior_art_status("bu-pa-3", "checked")

        unit = store.get_buildable_unit("bu-pa-3")
        assert unit.prior_art_status == "checked"

    def test_delete_prior_art_matches(self, store: Store) -> None:
        """Delete all prior art matches for a unit."""
        store.insert_buildable_unit(_make_unit("bu-pa-4"))

        match1 = {"source": "github", "title": "Match 1", "url": "https://a.com/1"}
        match2 = {"source": "github", "title": "Match 2", "url": "https://a.com/2"}

        store.insert_prior_art_match("bu-pa-4", match1)
        store.insert_prior_art_match("bu-pa-4", match2)

        assert len(store.get_prior_art_matches("bu-pa-4")) == 2

        deleted = store.delete_prior_art_matches("bu-pa-4")
        assert deleted == 2
        assert store.get_prior_art_matches("bu-pa-4") == []

    def test_prior_art_matches_ordered_by_relevance(self, store: Store) -> None:
        """Prior art matches should be ordered by relevance score descending."""
        store.insert_buildable_unit(_make_unit("bu-pa-5"))

        match1 = {"source": "github", "title": "Low", "url": "https://a.com/low", "relevance_score": 0.3}
        match2 = {"source": "github", "title": "High", "url": "https://a.com/high", "relevance_score": 0.9}
        match3 = {"source": "github", "title": "Medium", "url": "https://a.com/med", "relevance_score": 0.6}

        store.insert_prior_art_match("bu-pa-5", match1)
        store.insert_prior_art_match("bu-pa-5", match2)
        store.insert_prior_art_match("bu-pa-5", match3)

        matches = store.get_prior_art_matches("bu-pa-5")
        assert matches[0]["title"] == "High"
        assert matches[1]["title"] == "Medium"
        assert matches[2]["title"] == "Low"


# ── Pipeline Run Domains ─────────────────────────────────────────────


class TestPipelineRunDomains:
    def test_insert_and_get_pipeline_run_domains(self, store: Store) -> None:
        """Insert and retrieve pipeline run domain stats."""
        store.insert_pipeline_run("run-prd-1", {"profile": "test"})

        stats = {
            "signals_fetched": 10,
            "insights_generated": 3,
            "ideas_generated": 2,
            "ideas_evaluated": 2,
            "avg_score": 75.5,
        }

        store.insert_pipeline_run_domain("run-prd-1", "mcp", stats)

        domains = store.get_pipeline_run_domains("run-prd-1")
        assert len(domains) == 1
        assert domains[0]["domain"] == "mcp"
        assert domains[0]["signals_fetched"] == 10
        assert domains[0]["avg_score"] == 75.5

    def test_get_pipeline_run_domains_empty(self, store: Store) -> None:
        """Get domains for run with no domain stats."""
        store.insert_pipeline_run("run-prd-2", {})
        assert store.get_pipeline_run_domains("run-prd-2") == []

    def test_get_domain_performance(self, store: Store) -> None:
        """Get performance history for a specific domain."""
        store.insert_pipeline_run("run-dp-1", {})
        store.insert_pipeline_run("run-dp-2", {})

        stats1 = {"signals_fetched": 5, "insights_generated": 2, "avg_score": 70.0}
        stats2 = {"signals_fetched": 8, "insights_generated": 3, "avg_score": 80.0}

        store.insert_pipeline_run_domain("run-dp-1", "ai", stats1)
        store.insert_pipeline_run_domain("run-dp-2", "ai", stats2)

        perf = store.get_domain_performance("ai", limit=10)
        assert len(perf) == 2
        # Should be ordered by run started_at DESC (newest first)
        assert perf[0]["run_id"] == "run-dp-2"
        assert perf[1]["run_id"] == "run-dp-1"

    def test_get_domain_performance_respects_limit(self, store: Store) -> None:
        """Domain performance should respect limit parameter."""
        for i in range(5):
            run_id = f"run-dpl-{i}"
            store.insert_pipeline_run(run_id, {})
            store.insert_pipeline_run_domain(run_id, "testing", {"signals_fetched": i})

        perf = store.get_domain_performance("testing", limit=3)
        assert len(perf) == 3


# ── Additional CRUD Coverage ─────────────────────────────────────────


class TestAdditionalCRUD:
    def test_count_buildable_units_with_filters(self, store: Store) -> None:
        """Count buildable units with status and domain filters."""
        u1 = _make_unit("bu-cnt-1")
        u1.status = "draft"
        u1.domain = "ai"

        u2 = _make_unit("bu-cnt-2")
        u2.status = "evaluated"
        u2.domain = "ai"

        u3 = _make_unit("bu-cnt-3")
        u3.status = "draft"
        u3.domain = "devtools"

        store.insert_buildable_unit(u1)
        store.insert_buildable_unit(u2)
        store.insert_buildable_unit(u3)

        assert store.count_buildable_units() == 3
        assert store.count_buildable_units(status="draft") == 2
        assert store.count_buildable_units(status="evaluated") == 1
        assert store.count_buildable_units(domain="ai") == 2
        assert store.count_buildable_units(status="draft", domain="ai") == 1

    def test_get_idea_status_summary(self, store: Store) -> None:
        """Summarize idea statuses with domain and recommendation breakdowns."""
        evaluated = _make_unit("bu-status-evaluated")
        evaluated.status = "evaluated"
        evaluated.domain = "ai"

        approved = _make_unit("bu-status-approved")
        approved.status = "approved"
        approved.domain = "ai"

        archived = _make_unit("bu-status-archived")
        archived.status = "archived"
        archived.domain = "devtools"

        store.insert_buildable_unit(evaluated)
        store.insert_buildable_unit(approved)
        store.insert_buildable_unit(archived)

        yes_eval = _make_evaluation(evaluated.id, overall_score=81.0)
        yes_eval.recommendation = "yes"
        maybe_eval = _make_evaluation(approved.id, overall_score=64.0)
        maybe_eval.recommendation = "maybe"
        store.insert_evaluation(yes_eval)
        store.insert_evaluation(maybe_eval)

        summary = store.get_idea_status_summary()

        assert summary["total"] == 3
        assert summary["totals"] == {
            "pending_review": 1,
            "approved": 1,
            "rejected": 0,
            "published": 0,
            "archived": 1,
            "duplicate": 0,
            "synthesized": 0,
        }
        assert {"status": "pending_review", "count": 1} in summary["by_status"]

        domains = {row["domain"]: row for row in summary["by_domain"]}
        assert domains["ai"]["count"] == 2
        assert domains["ai"]["statuses"] == {"approved": 1, "pending_review": 1}
        assert domains["devtools"]["statuses"] == {"archived": 1}

        recommendations = {row["recommendation"]: row for row in summary["by_recommendation"]}
        assert recommendations["yes"]["statuses"] == {"pending_review": 1}
        assert recommendations["maybe"]["statuses"] == {"approved": 1}
        assert {row["recommendation"] for row in summary["groups"]} == {"yes", "maybe", None}

    def test_get_buildable_units_with_domain_filter(self, store: Store) -> None:
        """Get buildable units filtered by domain."""
        u1 = _make_unit("bu-dom-1")
        u1.domain = "mcp"

        u2 = _make_unit("bu-dom-2")
        u2.domain = "ai"

        store.insert_buildable_unit(u1)
        store.insert_buildable_unit(u2)

        mcp_units = store.get_buildable_units(domain="mcp")
        assert len(mcp_units) == 1
        assert mcp_units[0].id == "bu-dom-1"

    def test_get_review_queue_returns_unreviewed_evaluated_ideas_by_score(self, store: Store) -> None:
        high = _make_unit("bu-review-high")
        high.status = "evaluated"
        high.domain = "devtools"
        low = _make_unit("bu-review-low")
        low.status = "evaluated"
        low.domain = "devtools"
        reviewed = _make_unit("bu-review-done")
        reviewed.status = "evaluated"
        draft = _make_unit("bu-review-draft")
        draft.status = "draft"

        for unit, score in [(high, 88.0), (low, 62.0), (reviewed, 91.0), (draft, 99.0)]:
            store.insert_buildable_unit(unit)
            store.insert_evaluation(_make_evaluation(unit.id, overall_score=score))
        store.insert_feedback(reviewed.id, "approved", "already reviewed")
        store.insert_idea_critique(
            high.id,
            {
                "buyer_clarity": 8.0,
                "quality_score": 7.5,
                "reasoning": "Clear buyer and workflow.",
                "rejection_tags": [],
            },
        )

        queue = store.get_review_queue()

        assert [row["unit"].id for row in queue] == ["bu-review-high", "bu-review-low"]
        assert [row["evaluation"].overall_score for row in queue] == [88.0, 62.0]
        assert queue[0]["latest_critique"]["dimensions"]["buyer_clarity"] == 8.0
        assert queue[0]["latest_critique"]["reasoning"] == "Clear buyer and workflow."

    def test_get_review_queue_filters_domain_min_score_and_limit(self, store: Store) -> None:
        seeds = [
            ("bu-review-ai-1", "ai", 90.0),
            ("bu-review-ai-2", "ai", 75.0),
            ("bu-review-dev-1", "devtools", 95.0),
        ]
        for unit_id, domain, score in seeds:
            unit = _make_unit(unit_id)
            unit.status = "evaluated"
            unit.domain = domain
            store.insert_buildable_unit(unit)
            store.insert_evaluation(_make_evaluation(unit.id, overall_score=score))

        queue = store.get_review_queue(domain="ai", min_score=80.0, limit=1)

        assert [row["unit"].id for row in queue] == ["bu-review-ai-1"]

    def test_has_feedback(self, store: Store) -> None:
        """Check if buildable unit has feedback."""
        store.insert_buildable_unit(_make_unit("bu-hf-1"))
        store.insert_buildable_unit(_make_unit("bu-hf-2"))

        assert not store.has_feedback("bu-hf-1")

        store.insert_feedback("bu-hf-1", "approved")

        assert store.has_feedback("bu-hf-1")
        assert not store.has_feedback("bu-hf-2")

    def test_get_latest_feedback(self, store: Store) -> None:
        unit = _make_unit("bu-latest-feedback")
        store.insert_buildable_unit(unit)
        assert store.get_latest_feedback(unit.id) is None

        store.insert_feedback(unit.id, "rejected", "first reason")
        store.insert_feedback(unit.id, "approved", "latest reason", approval_score=8)

        latest = store.get_latest_feedback(unit.id)
        assert latest is not None
        assert latest["outcome"] == "approved"
        assert latest["reason"] == "latest reason"
        assert latest["approval_score"] == 8

    def test_get_feedback_log(self, store: Store) -> None:
        """Get feedback log with unit and evaluation details."""
        store.insert_buildable_unit(_make_unit("bu-fl-1"))
        store.insert_evaluation(_make_evaluation("bu-fl-1", overall_score=85.0))
        store.insert_feedback("bu-fl-1", "approved", "excellent idea")

        log = store.get_feedback_log(limit=10)
        assert len(log) == 1
        assert log[0]["unit_id"] == "bu-fl-1"
        assert log[0]["outcome"] == "approved"
        assert log[0]["reason"] == "excellent idea"
        assert log[0]["score"] == 85.0
        assert log[0]["recommendation"] == "yes"

    def test_count_insights(self, store: Store) -> None:
        """Count total insights."""
        assert store.count_insights() == 0

        ins = Insight(
            id="ins-cnt-1",
            category=InsightCategory.GAP,
            title="Test",
            summary="Test",
            evidence=[],
            confidence=0.5,
            domains=[],
            implications=[],
            time_horizon="near_term",
        )
        store.insert_insight(ins)

        assert store.count_insights() == 1


# ── Concurrent Connections ───────────────────────────────────────────


class TestConcurrentConnections:
    def test_multiple_stores_same_db(self, tmp_path: Path) -> None:
        """Multiple Store instances can connect to the same database."""
        db_path = str(tmp_path / "concurrent.db")

        # First store writes data
        with Store(db_path=db_path) as s1:
            sig = _make_signal(sig_id="sig-conc-1", url="https://a.com/conc1")
            s1.insert_signal(sig)

        # Second store reads it
        with Store(db_path=db_path) as s2:
            retrieved = s2.get_signal("sig-conc-1")
            assert retrieved is not None
            assert retrieved.id == "sig-conc-1"

    def test_wal_mode_supports_concurrent_reads(self, tmp_path: Path) -> None:
        """WAL mode allows concurrent readers."""
        db_path = str(tmp_path / "wal_concurrent.db")

        # Initialize with WAL mode
        with Store(db_path=db_path, wal_mode=True) as s1:
            sig = _make_signal(sig_id="sig-wal-1", url="https://a.com/wal1")
            s1.insert_signal(sig)

        # Open two concurrent readers
        s2 = Store(db_path=db_path, wal_mode=True)
        s3 = Store(db_path=db_path, wal_mode=True)

        try:
            # Both should be able to read
            assert s2.get_signal("sig-wal-1") is not None
            assert s3.get_signal("sig-wal-1") is not None
        finally:
            s2.close()
            s3.close()
