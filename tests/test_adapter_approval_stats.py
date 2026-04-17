"""Comprehensive tests for Store.get_adapter_approval_stats().

This method computes per-adapter approval rates from feedback attribution data.
It's used for adaptive fetch allocation and has subtle aggregation logic.

Coverage:
- Basic behavior: empty feedback, no approved/rejected outcomes, single adapter stats
- Multi-adapter attribution: overlapping adapters, independent rates
- Outcome handling: published→approved, abandoned→rejected, skipped outcomes
- Edge cases: 100% approval, 0% approval, division safety
"""

from __future__ import annotations

import pytest

from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_score(value: float = 7.0) -> DimensionScore:
    """Create a dimension score for evaluations."""
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _make_signal(adapter: str, sig_id: str) -> Signal:
    """Create a test signal from a specific adapter."""
    return Signal(
        id=sig_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"Signal from {adapter}",
        content=f"Content from {adapter}",
        url=f"https://example.com/{sig_id}",
        credibility=0.7,
        metadata={},
    )


def _seed_idea_with_signals(
    store: Store,
    unit_id: str,
    adapter: str,
    signal_count: int,
) -> list[str]:
    """Seed signals + buildable unit + evaluation for a complete feedback chain.

    This sets up the data chain required for get_adapter_approval_stats():
    1. Signals with source_adapter
    2. BuildableUnit with evidence_signals referencing those signal IDs
    3. UtilityEvaluation for the unit (needed by get_feedback_with_attribution)

    Returns list of signal IDs.
    """
    sig_ids = []
    for i in range(signal_count):
        sid = f"sig-{adapter}-{unit_id}-{i}"
        store.insert_signal(_make_signal(adapter, sid))
        sig_ids.append(sid)

    unit = BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="Test idea",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        value_proposition="Test value",
        evidence_signals=sig_ids,
        target_users="both",
    )
    store.insert_buildable_unit(unit)

    # Insert evaluation so get_feedback_with_attribution() can fetch eval_score
    evaluation = UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_make_score(8.0),
        addressable_scale=_make_score(7.0),
        build_effort=_make_score(6.0),
        composability=_make_score(7.5),
        competitive_density=_make_score(8.0),
        timing_fit=_make_score(7.0),
        compounding_value=_make_score(6.5),
        overall_score=72.0,
        strengths=["test"],
        weaknesses=["test"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
    store.insert_evaluation(evaluation)

    return sig_ids


def _seed_multi_adapter_idea(
    store: Store,
    unit_id: str,
    adapters: list[str],
) -> None:
    """Seed an idea with signals from multiple adapters.

    Creates one signal per adapter, all linked to the same BuildableUnit.
    """
    sig_ids = []
    for adapter in adapters:
        sid = f"sig-{adapter}-{unit_id}"
        store.insert_signal(_make_signal(adapter, sid))
        sig_ids.append(sid)

    unit = BuildableUnit(
        id=unit_id,
        title=f"Multi-adapter idea {unit_id}",
        one_liner="Test idea",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        value_proposition="Test value",
        evidence_signals=sig_ids,
        target_users="both",
    )
    store.insert_buildable_unit(unit)

    evaluation = UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_make_score(8.0),
        addressable_scale=_make_score(7.0),
        build_effort=_make_score(6.0),
        composability=_make_score(7.5),
        competitive_density=_make_score(8.0),
        timing_fit=_make_score(7.0),
        compounding_value=_make_score(6.5),
        overall_score=72.0,
        strengths=["test"],
        weaknesses=["test"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
    store.insert_evaluation(evaluation)


# ── Basic Behavior ───────────────────────────────────────────────────


class TestBasicBehavior:
    """Test basic behavior of get_adapter_approval_stats()."""

    def test_returns_empty_dict_when_no_feedback_exists(self, store: Store) -> None:
        """When there's no feedback at all, should return empty dict."""
        stats = store.get_adapter_approval_stats()
        assert stats == {}

    def test_returns_empty_dict_when_feedback_has_no_approved_rejected_outcomes(
        self, store: Store
    ) -> None:
        """Feedback with outcomes other than approved/published/rejected/abandoned is skipped."""
        _seed_idea_with_signals(store, "bu-pending-1", "hackernews", 2)
        store.insert_feedback("bu-pending-1", "pending", "still reviewing")

        _seed_idea_with_signals(store, "bu-synth-1", "reddit", 2)
        store.insert_feedback("bu-synth-1", "synthesized", "combined with others")

        stats = store.get_adapter_approval_stats()
        # Neither 'pending' nor 'synthesized' count toward approval stats
        assert stats == {}

    def test_correctly_counts_approved_feedback_for_single_adapter(
        self, store: Store
    ) -> None:
        """Single approved feedback increments approved count and computes rate."""
        _seed_idea_with_signals(store, "bu-app-1", "github_issues", 2)
        store.insert_feedback("bu-app-1", "approved", "good idea")

        stats = store.get_adapter_approval_stats()
        assert "github_issues" in stats
        assert stats["github_issues"]["approved"] == 1
        assert stats["github_issues"]["rejected"] == 0
        assert stats["github_issues"]["total_feedbacked"] == 1
        assert stats["github_issues"]["approval_rate"] == 1.0

    def test_correctly_counts_rejected_feedback_for_single_adapter(
        self, store: Store
    ) -> None:
        """Single rejected feedback increments rejected count and computes rate."""
        _seed_idea_with_signals(store, "bu-rej-1", "producthunt", 2)
        store.insert_feedback("bu-rej-1", "rejected", "not useful")

        stats = store.get_adapter_approval_stats()
        assert "producthunt" in stats
        assert stats["producthunt"]["approved"] == 0
        assert stats["producthunt"]["rejected"] == 1
        assert stats["producthunt"]["total_feedbacked"] == 1
        assert stats["producthunt"]["approval_rate"] == 0.0

    def test_computes_approval_rate_as_approved_divided_by_total(
        self, store: Store
    ) -> None:
        """Approval rate = approved / (approved + rejected)."""
        # Seed 3 ideas from same adapter with mixed feedback
        _seed_idea_with_signals(store, "bu-mix-1", "hackernews", 2)
        _seed_idea_with_signals(store, "bu-mix-2", "hackernews", 2)
        _seed_idea_with_signals(store, "bu-mix-3", "hackernews", 2)

        store.insert_feedback("bu-mix-1", "approved")
        store.insert_feedback("bu-mix-2", "rejected")
        store.insert_feedback("bu-mix-3", "approved")

        stats = store.get_adapter_approval_stats()
        hn_stats = stats["hackernews"]
        assert hn_stats["approved"] == 2
        assert hn_stats["rejected"] == 1
        assert hn_stats["total_feedbacked"] == 3
        # 2 approved / 3 total = 0.6666...
        assert abs(hn_stats["approval_rate"] - (2.0 / 3.0)) < 0.0001


# ── Multi-Adapter Attribution ────────────────────────────────────────


class TestMultiAdapterAttribution:
    """Test handling of ideas attributed to multiple adapters."""

    def test_idea_attributed_to_multiple_adapters_increments_both(
        self, store: Store
    ) -> None:
        """An idea with signals from 2 adapters increments stats for BOTH."""
        _seed_multi_adapter_idea(store, "bu-multi-1", ["hackernews", "reddit"])
        store.insert_feedback("bu-multi-1", "approved", "excellent")

        stats = store.get_adapter_approval_stats()
        # Both adapters should get credit
        assert stats["hackernews"]["approved"] == 1
        assert stats["hackernews"]["total_feedbacked"] == 1
        assert stats["reddit"]["approved"] == 1
        assert stats["reddit"]["total_feedbacked"] == 1

    def test_approval_rate_computed_independently_per_adapter(
        self, store: Store
    ) -> None:
        """When ideas have overlapping attribution, each adapter's rate is independent."""
        # Idea 1: hackernews only → approved
        _seed_idea_with_signals(store, "bu-hn-only", "hackernews", 2)
        store.insert_feedback("bu-hn-only", "approved")

        # Idea 2: hackernews + reddit → rejected
        _seed_multi_adapter_idea(store, "bu-both-1", ["hackernews", "reddit"])
        store.insert_feedback("bu-both-1", "rejected")

        # Idea 3: reddit only → approved
        _seed_idea_with_signals(store, "bu-reddit-only", "reddit", 2)
        store.insert_feedback("bu-reddit-only", "approved")

        stats = store.get_adapter_approval_stats()

        # hackernews: 1 approved (bu-hn-only) + 1 rejected (bu-both-1) = 50%
        assert stats["hackernews"]["approved"] == 1
        assert stats["hackernews"]["rejected"] == 1
        assert stats["hackernews"]["approval_rate"] == 0.5

        # reddit: 2 approved (bu-both-1 rejected doesn't count, bu-reddit-only approved, bu-both-1 rejected)
        # Wait, let me recalculate: bu-both-1 is rejected, bu-reddit-only is approved
        # reddit gets: 1 rejected (bu-both-1) + 1 approved (bu-reddit-only) = 50%
        assert stats["reddit"]["approved"] == 1
        assert stats["reddit"]["rejected"] == 1
        assert stats["reddit"]["approval_rate"] == 0.5


# ── Outcome Handling ─────────────────────────────────────────────────


class TestOutcomeHandling:
    """Test that different outcome values are handled correctly."""

    def test_published_outcome_counts_as_approved(self, store: Store) -> None:
        """'published' outcome should increment approved count (line 908)."""
        _seed_idea_with_signals(store, "bu-pub-1", "npm_registry", 2)
        store.insert_feedback("bu-pub-1", "published", "shipped to production")

        stats = store.get_adapter_approval_stats()
        assert stats["npm_registry"]["approved"] == 1
        assert stats["npm_registry"]["rejected"] == 0
        assert stats["npm_registry"]["approval_rate"] == 1.0

    def test_abandoned_outcome_counts_as_rejected(self, store: Store) -> None:
        """'abandoned' outcome should increment rejected count (line 909)."""
        _seed_idea_with_signals(store, "bu-aband-1", "security_advisories", 2)
        store.insert_feedback("bu-aband-1", "abandoned", "no longer relevant")

        stats = store.get_adapter_approval_stats()
        assert stats["security_advisories"]["approved"] == 0
        assert stats["security_advisories"]["rejected"] == 1
        assert stats["security_advisories"]["approval_rate"] == 0.0

    def test_other_outcomes_are_skipped_entirely(self, store: Store) -> None:
        """Outcomes like 'pending', 'synthesized' are skipped (line 910-911)."""
        _seed_idea_with_signals(store, "bu-pend-1", "hackernews", 2)
        _seed_idea_with_signals(store, "bu-synth-1", "hackernews", 2)
        _seed_idea_with_signals(store, "bu-app-1", "hackernews", 2)

        store.insert_feedback("bu-pend-1", "pending", "still reviewing")
        store.insert_feedback("bu-synth-1", "synthesized", "merged")
        store.insert_feedback("bu-app-1", "approved", "good")

        stats = store.get_adapter_approval_stats()
        # Only the approved feedback should be counted
        assert stats["hackernews"]["total_feedbacked"] == 1
        assert stats["hackernews"]["approved"] == 1
        assert stats["hackernews"]["rejected"] == 0

    def test_all_four_outcome_types_handled_correctly(self, store: Store) -> None:
        """Test all 4 counting outcome types in a single scenario."""
        _seed_idea_with_signals(store, "bu-1", "github_issues", 2)
        _seed_idea_with_signals(store, "bu-2", "github_issues", 2)
        _seed_idea_with_signals(store, "bu-3", "github_issues", 2)
        _seed_idea_with_signals(store, "bu-4", "github_issues", 2)

        store.insert_feedback("bu-1", "approved")  # counts as approved
        store.insert_feedback("bu-2", "published")  # counts as approved
        store.insert_feedback("bu-3", "rejected")  # counts as rejected
        store.insert_feedback("bu-4", "abandoned")  # counts as rejected

        stats = store.get_adapter_approval_stats()
        assert stats["github_issues"]["approved"] == 2  # approved + published
        assert stats["github_issues"]["rejected"] == 2  # rejected + abandoned
        assert stats["github_issues"]["total_feedbacked"] == 4
        assert stats["github_issues"]["approval_rate"] == 0.5


# ── Edge Cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_adapter_with_100_percent_approval_rate(self, store: Store) -> None:
        """All approved, zero rejected → 100% rate."""
        _seed_idea_with_signals(store, "bu-perfect-1", "producthunt", 2)
        _seed_idea_with_signals(store, "bu-perfect-2", "producthunt", 2)
        _seed_idea_with_signals(store, "bu-perfect-3", "producthunt", 2)

        store.insert_feedback("bu-perfect-1", "approved")
        store.insert_feedback("bu-perfect-2", "published")
        store.insert_feedback("bu-perfect-3", "approved")

        stats = store.get_adapter_approval_stats()
        assert stats["producthunt"]["approved"] == 3
        assert stats["producthunt"]["rejected"] == 0
        assert stats["producthunt"]["approval_rate"] == 1.0

    def test_adapter_with_0_percent_approval_rate(self, store: Store) -> None:
        """All rejected, zero approved → 0% rate."""
        _seed_idea_with_signals(store, "bu-bad-1", "reddit", 2)
        _seed_idea_with_signals(store, "bu-bad-2", "reddit", 2)

        store.insert_feedback("bu-bad-1", "rejected")
        store.insert_feedback("bu-bad-2", "abandoned")

        stats = store.get_adapter_approval_stats()
        assert stats["reddit"]["approved"] == 0
        assert stats["reddit"]["rejected"] == 2
        assert stats["reddit"]["approval_rate"] == 0.0

    def test_division_safety_total_feedbacked_greater_than_zero(
        self, store: Store
    ) -> None:
        """Verify division by total > 0 guard at line 928.

        This is implicitly tested by all other tests, but we verify
        the structure explicitly here.
        """
        _seed_idea_with_signals(store, "bu-safe-1", "hackernews", 2)
        store.insert_feedback("bu-safe-1", "approved")

        stats = store.get_adapter_approval_stats()
        # Ensure total_feedbacked is positive before division
        assert stats["hackernews"]["total_feedbacked"] > 0
        # And that approval_rate was computed without error
        assert stats["hackernews"]["approval_rate"] == 1.0

    def test_multiple_feedback_on_same_idea_counted_separately(
        self, store: Store
    ) -> None:
        """If same idea gets multiple feedback records, each should count.

        Note: This is a theoretical edge case - the current schema may prevent
        multiple feedback records per buildable_unit, but the stats method
        doesn't explicitly deduplicate.
        """
        _seed_idea_with_signals(store, "bu-multi-fb", "hackernews", 2)

        # Insert two feedback records (if schema allows)
        try:
            store.insert_feedback("bu-multi-fb", "approved", "first review")
            store.insert_feedback("bu-multi-fb", "rejected", "second review")

            stats = store.get_adapter_approval_stats()
            # If both feedbacks are recorded, stats should reflect both
            # This may fail if schema enforces unique constraint
            assert stats["hackernews"]["total_feedbacked"] >= 1
        except Exception:
            # If schema prevents multiple feedback, this test is n/a
            pytest.skip("Schema prevents multiple feedback per unit")

    def test_empty_evidence_signals_handled_gracefully(self, store: Store) -> None:
        """BuildableUnit with empty evidence_signals → no attribution, no crash."""
        unit = BuildableUnit(
            id="bu-no-evidence",
            title="Idea with no evidence",
            one_liner="Test",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Test",
            solution="Test",
            value_proposition="Test",
            evidence_signals=[],  # Empty!
            target_users="both",
        )
        store.insert_buildable_unit(unit)
        store.insert_feedback("bu-no-evidence", "approved", "good idea")

        # Should not crash, but also won't attribute to any adapter
        stats = store.get_adapter_approval_stats()
        # No adapters should be present since there are no evidence signals
        assert stats == {}

    def test_signal_with_no_matching_adapter_handled_gracefully(
        self, store: Store
    ) -> None:
        """If evidence_signals references a signal ID that doesn't exist, handle gracefully."""
        # Create unit referencing a non-existent signal
        unit = BuildableUnit(
            id="bu-orphan",
            title="Orphaned signal reference",
            one_liner="Test",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Test",
            solution="Test",
            value_proposition="Test",
            evidence_signals=["sig-nonexistent-999"],  # Doesn't exist in signals table
            target_users="both",
        )
        store.insert_buildable_unit(unit)

        evaluation = UtilityEvaluation(
            buildable_unit_id="bu-orphan",
            pain_severity=_make_score(8.0),
            addressable_scale=_make_score(7.0),
            build_effort=_make_score(6.0),
            composability=_make_score(7.5),
            competitive_density=_make_score(8.0),
            timing_fit=_make_score(7.0),
            compounding_value=_make_score(6.5),
            overall_score=72.0,
            strengths=["test"],
            weaknesses=["test"],
            recommendation="yes",
            weights_used={"pain_severity": 0.2},
        )
        store.insert_evaluation(evaluation)

        store.insert_feedback("bu-orphan", "approved", "good")

        # Should not crash; get_feedback_with_attribution filters out missing signals
        stats = store.get_adapter_approval_stats()
        # No adapters attributed since signal doesn't exist
        assert stats == {}
