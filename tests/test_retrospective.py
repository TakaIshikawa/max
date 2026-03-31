"""Tests for retrospective analysis — rule-based feedback pattern extraction."""

from __future__ import annotations

from max.analysis.retrospective import (
    RetrospectiveContext,
    analyze_retrospective,
    format_retrospective_for_ideation,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


def _make_score(value: float = 7.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _seed_feedback(
    store: Store,
    unit_id: str,
    adapter: str,
    outcome: str,
    *,
    category: str = "cli_tool",
    target_users: str = "both",
    eval_score: float = 70.0,
) -> None:
    """Seed signal + unit + evaluation + feedback for one idea."""
    sig_id = f"sig-{unit_id}"
    sig = Signal(
        id=sig_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"Signal for {unit_id}",
        content=f"Content for {unit_id}",
        url=f"https://example.com/{sig_id}",
        credibility=0.7,
        metadata={"signal_role": "problem"},
    )
    store.insert_signal(sig)

    unit = BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="Test",
        category=BuildableCategory(category),
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        value_proposition="Test value",
        evidence_signals=[sig_id],
        target_users=target_users,
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
        overall_score=eval_score,
        strengths=["test"],
        weaknesses=["test"],
        recommendation="yes" if outcome == "approved" else "no",
        weights_used={"pain_severity": 0.2},
    )
    store.insert_evaluation(evaluation)
    store.insert_feedback(unit_id, outcome)


# ── Insufficient data ────────────────────────────────────────────


def test_no_feedback_returns_none(store: Store) -> None:
    """No feedback at all → None."""
    assert analyze_retrospective(store) is None


def test_insufficient_outcomes_returns_none(store: Store) -> None:
    """Less than min_outcomes → None."""
    _seed_feedback(store, "bu-1", "hn", "approved")
    _seed_feedback(store, "bu-2", "hn", "rejected")
    assert analyze_retrospective(store, min_outcomes=4) is None


def test_all_same_outcome_returns_none(store: Store) -> None:
    """All approved (no diversity) → None."""
    for i in range(5):
        _seed_feedback(store, f"bu-same-{i}", "hn", "approved")
    assert analyze_retrospective(store) is None


# ── Category analysis ────────────────────────────────────────────


def test_successful_and_failed_categories(store: Store) -> None:
    """Categories with >50% approval are successful, <30% are failed."""
    # cli_tool: 3 approved, 1 rejected → 75% → successful
    for i in range(3):
        _seed_feedback(store, f"bu-cli-a-{i}", "hn", "approved", category="cli_tool")
    _seed_feedback(store, "bu-cli-r-1", "hn", "rejected", category="cli_tool")

    # application: 1 approved, 3 rejected → 25% → failed
    _seed_feedback(store, "bu-app-a-1", "reddit", "approved", category="application")
    for i in range(3):
        _seed_feedback(store, f"bu-app-r-{i}", "reddit", "rejected", category="application")

    ctx = analyze_retrospective(store)
    assert ctx is not None
    assert "cli_tool" in ctx.successful_categories
    assert "application" in ctx.failed_categories


# ── Adapter analysis ─────────────────────────────────────────────


def test_successful_and_underperforming_adapters(store: Store) -> None:
    """Adapters with >50% approval are successful, <30% underperform."""
    # hackernews: 3 approved, 0 rejected → 100% → successful
    for i in range(3):
        _seed_feedback(store, f"bu-hn-a-{i}", "hackernews", "approved")

    # reddit: 0 approved, 3 rejected → 0% → underperforming
    for i in range(3):
        _seed_feedback(store, f"bu-rd-r-{i}", "reddit", "rejected")

    ctx = analyze_retrospective(store)
    assert ctx is not None
    assert "hackernews" in ctx.successful_adapters
    assert "reddit" in ctx.underperforming_adapters


# ── Target users ─────────────────────────────────────────────────


def test_preferred_target_users(store: Store) -> None:
    """The target_users with highest approval rate is preferred."""
    # both: 3 approved, 1 rejected → 75%
    for i in range(3):
        _seed_feedback(store, f"bu-both-a-{i}", "hn", "approved", target_users="both")
    _seed_feedback(store, "bu-both-r-1", "hn", "rejected", target_users="both")

    # humans: 1 approved, 3 rejected → 25%
    _seed_feedback(store, "bu-human-a-1", "hn", "approved", target_users="humans")
    for i in range(3):
        _seed_feedback(store, f"bu-human-r-{i}", "hn", "rejected", target_users="humans")

    ctx = analyze_retrospective(store)
    assert ctx is not None
    assert ctx.preferred_target_users == "both"


# ── Score calibration ────────────────────────────────────────────


def test_avg_score_computation(store: Store) -> None:
    """Average scores for approved vs rejected should be computed."""
    _seed_feedback(store, "bu-high-1", "hn", "approved", eval_score=80.0)
    _seed_feedback(store, "bu-high-2", "hn", "approved", eval_score=70.0)
    _seed_feedback(store, "bu-low-1", "hn", "rejected", eval_score=40.0)
    _seed_feedback(store, "bu-low-2", "hn", "rejected", eval_score=50.0)

    ctx = analyze_retrospective(store)
    assert ctx is not None
    assert ctx.avg_approved_score == 75.0  # (80 + 70) / 2
    assert ctx.avg_rejected_score == 45.0  # (40 + 50) / 2


# ── Pattern count ────────────────────────────────────────────────


def test_pattern_count(store: Store) -> None:
    """pattern_count should equal total feedback records analyzed."""
    for i in range(3):
        _seed_feedback(store, f"bu-cnt-a-{i}", "hn", "approved")
    for i in range(2):
        _seed_feedback(store, f"bu-cnt-r-{i}", "hn", "rejected")

    ctx = analyze_retrospective(store)
    assert ctx is not None
    assert ctx.pattern_count == 5


# ── Formatting ───────────────────────────────────────────────────


def test_format_none_returns_none() -> None:
    assert format_retrospective_for_ideation(None) is None


def test_ideation_prompt_includes_learned_context() -> None:
    """Ideation prompt should include learned context when provided."""
    from max.ideation.prompts import build_ideation_prompt

    prompt = build_ideation_prompt(
        '[]',
        learned_context="HISTORICAL PATTERNS (from 10 feedback outcomes):\n- Categories that work well: mcp_server",
    )
    assert "HISTORICAL PATTERNS" in prompt
    assert "mcp_server" in prompt


def test_cross_domain_prompt_includes_learned_context() -> None:
    """Cross-domain prompt should include learned context when provided."""
    from max.ideation.prompts import build_cross_domain_prompt

    prompt = build_cross_domain_prompt(
        '[]', '[]',
        learned_context="HISTORICAL PATTERNS (from 5 outcomes):\n- Best adapters: hackernews",
    )
    assert "HISTORICAL PATTERNS" in prompt
    assert "hackernews" in prompt


def test_format_output_structure() -> None:
    """Output should contain key sections."""
    ctx = RetrospectiveContext(
        successful_categories=["mcp_server"],
        failed_categories=["application"],
        successful_adapters=["hackernews"],
        underperforming_adapters=["reddit"],
        preferred_target_users="both",
        avg_approved_score=75.0,
        avg_rejected_score=45.0,
        pattern_count=10,
    )
    output = format_retrospective_for_ideation(ctx)
    assert output is not None
    assert "HISTORICAL PATTERNS (from 10 feedback outcomes)" in output
    assert "mcp_server" in output
    assert "application" in output
    assert "hackernews" in output
    assert "reddit" in output
    assert "both" in output
    assert "75.0" in output
    assert "45.0" in output
    assert "Prioritize" in output
