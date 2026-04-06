"""Integration tests for adaptive fetch strategy — end-to-end with real Store.

Verifies the full feedback loop: signals → insights/ideas → feedback → allocation.
Unlike unit tests that mock store data, these tests seed a real SQLite-backed Store
and exercise get_adapter_quality_stats() and get_adapter_approval_stats() together
with compute_fetch_allocation().
"""

from __future__ import annotations

from max.pipeline.fetch_strategy import compute_fetch_allocation
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────


def _make_signal(adapter: str, sig_id: str) -> Signal:
    return Signal(
        id=sig_id,
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter,
        title=f"Signal from {adapter}",
        content=f"Content from {adapter}",
        url=f"https://example.com/{sig_id}",
        credibility=0.7,
        metadata={"signal_role": "market"},
    )


def _make_score(value: float = 7.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _insert_signals(store: Store, adapter: str, count: int) -> list[str]:
    """Insert N signals for an adapter. Returns signal IDs."""
    sig_ids = []
    for i in range(count):
        sig_id = f"sig-{adapter}-{i}"
        store.insert_signal(_make_signal(adapter, sig_id))
        sig_ids.append(sig_id)
    return sig_ids


def _insert_insight(store: Store, insight_id: str, evidence: list[str]) -> None:
    store.insert_insight(
        Insight(
            id=insight_id,
            category=InsightCategory.GAP,
            title=f"Insight {insight_id}",
            summary="Test insight",
            evidence=evidence,
            confidence=0.8,
            domains=["test"],
        )
    )


def _insert_idea_with_feedback(
    store: Store,
    adapter: str,
    unit_id: str,
    evidence_signals: list[str],
    outcome: str,
) -> None:
    """Insert a buildable unit linked to signals, with evaluation and feedback."""
    unit = BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="Test idea",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        value_proposition="Test value",
        evidence_signals=evidence_signals,
    )
    store.insert_buildable_unit(unit)

    evaluation = UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_make_score(7.0),
        addressable_scale=_make_score(6.0),
        build_effort=_make_score(7.0),
        composability=_make_score(7.0),
        competitive_density=_make_score(7.0),
        timing_fit=_make_score(7.0),
        compounding_value=_make_score(7.0),
        overall_score=70.0,
        strengths=["test"],
        weaknesses=["test"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
    store.insert_evaluation(evaluation)
    store.insert_feedback(unit_id, outcome)


ADAPTERS = ["hackernews", "reddit", "github", "npm_registry"]


def _seed_full_scenario(store: Store) -> None:
    """Seed realistic data for 4 adapters with varying quality profiles.

    hackernews:   20 signals, 12 in insights, 10 in ideas, 5 approved / 0 rejected
    reddit:       15 signals, 5 in insights, 4 in ideas, 2 approved / 2 rejected
    github:       10 signals, 1 in insights, 1 in ideas, 0 approved / 3 rejected
    npm_registry: 5 signals, 3 in insights, 3 in ideas, 3 approved / 0 rejected
    """
    # -- hackernews: high quality, high approval --
    hn_ids = _insert_signals(store, "hackernews", 20)
    _insert_insight(store, "ins-hn-0", hn_ids[:6])
    _insert_insight(store, "ins-hn-1", hn_ids[6:12])
    for i in range(5):
        _insert_idea_with_feedback(
            store, "hackernews", f"bu-hn-{i}", hn_ids[i * 2 : i * 2 + 2], "approved"
        )

    # -- reddit: medium quality, mixed approval --
    rd_ids = _insert_signals(store, "reddit", 15)
    _insert_insight(store, "ins-rd-0", rd_ids[:5])
    for i in range(2):
        _insert_idea_with_feedback(
            store, "reddit", f"bu-rd-app-{i}", rd_ids[i * 2 : i * 2 + 2], "approved"
        )
    for i in range(2):
        _insert_idea_with_feedback(
            store, "reddit", f"bu-rd-rej-{i}", rd_ids[4 + i * 2 : 4 + i * 2 + 2], "rejected"
        )

    # -- github: low quality, mostly rejected --
    gh_ids = _insert_signals(store, "github", 10)
    _insert_insight(store, "ins-gh-0", gh_ids[:1])
    for i in range(3):
        _insert_idea_with_feedback(
            store, "github", f"bu-gh-{i}", gh_ids[i : i + 1], "rejected"
        )

    # -- npm_registry: small but high quality, all approved --
    npm_ids = _insert_signals(store, "npm_registry", 5)
    _insert_insight(store, "ins-npm-0", npm_ids[:3])
    for i in range(3):
        _insert_idea_with_feedback(
            store, "npm_registry", f"bu-npm-{i}", npm_ids[i : i + 1], "approved"
        )


# ── 1. Quality-based allocation ─────────────────────────────────


def test_quality_based_allocation(store: Store) -> None:
    """With full historical data, higher-quality adapters get larger allocations."""
    _seed_full_scenario(store)

    allocation = compute_fetch_allocation(
        total_budget=100, adapter_names=ADAPTERS, store=store
    )

    # Basic shape
    assert set(allocation.keys()) == set(ADAPTERS)
    assert all(isinstance(v, int) for v in allocation.values())
    assert sum(allocation.values()) == 100

    # Minimum floor
    for v in allocation.values():
        assert v >= 3

    # High-quality adapters beat low-quality
    assert allocation["hackernews"] > allocation["github"]
    assert allocation["npm_registry"] > allocation["github"]


# ── 2. Uniform fallback (cold start) ────────────────────────────


def test_uniform_fallback_no_data(store: Store) -> None:
    """Fresh store with zero history gives roughly equal allocations."""
    allocation = compute_fetch_allocation(
        total_budget=100, adapter_names=ADAPTERS, store=store
    )

    assert set(allocation.keys()) == set(ADAPTERS)
    assert sum(allocation.values()) == 100

    for v in allocation.values():
        assert 20 <= v <= 30, f"Expected roughly uniform (~25), got {v}"


# ── 3. Insufficient feedback (signals but no feedback) ───────────


def test_insufficient_feedback_uses_quality_only(store: Store) -> None:
    """With signals and insights but no feedback, allocation uses utilization rates."""
    # hackernews: 10 signals, 5 referenced in insights (50% insight rate)
    hn_ids = _insert_signals(store, "hackernews", 10)
    _insert_insight(store, "ins-hn-nofb", hn_ids[:5])

    # Insert ideas linked to hackernews signals (but no feedback)
    unit = BuildableUnit(
        id="bu-hn-nofb",
        title="HN idea",
        one_liner="Test",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test",
        solution="Test",
        value_proposition="Test",
        evidence_signals=hn_ids[:5],
    )
    store.insert_buildable_unit(unit)

    # github: 10 signals, none referenced
    _insert_signals(store, "github", 10)

    allocation = compute_fetch_allocation(
        total_budget=60, adapter_names=["hackernews", "github"], store=store
    )

    assert sum(allocation.values()) == 60
    # hackernews has higher utilization, should get more
    assert allocation["hackernews"] > allocation["github"]


# ── 4. Single adapter gets full budget ──────────────────────────


def test_single_adapter_gets_full_budget(store: Store) -> None:
    """A single adapter receives the entire budget."""
    _insert_signals(store, "hackernews", 10)

    allocation = compute_fetch_allocation(
        total_budget=100, adapter_names=["hackernews"], store=store
    )

    assert allocation == {"hackernews": 100}


# ── 5. Budget reconciliation (min > total) ──────────────────────


def test_budget_less_than_min_sum(store: Store) -> None:
    """When total_budget < min_per_adapter * n, gracefully distributes budget."""
    allocation = compute_fetch_allocation(
        total_budget=10,
        adapter_names=ADAPTERS,
        store=store,
        min_per_adapter=3,
    )

    # 4*3=12 > 10, so the function should handle this
    assert set(allocation.keys()) == set(ADAPTERS)
    # Each adapter gets floor(10/4) = 2
    assert sum(allocation.values()) == 8  # 4 * 2 = 8 (capped per-adapter)
    for v in allocation.values():
        assert v >= 1


# ── 6. Weight parameters affect allocation ──────────────────────


def test_weight_parameters_change_allocation(store: Store) -> None:
    """Different insight_weight / idea_weight values shift allocation."""
    # One adapter with high insight rate, low idea rate
    hn_ids = _insert_signals(store, "hackernews", 10)
    _insert_insight(store, "ins-hn-wt", hn_ids[:8])  # 80% insight hit rate
    # No ideas from hackernews

    # Another adapter with low insight rate, high idea rate
    gh_ids = _insert_signals(store, "github", 10)
    # No insights from github
    unit = BuildableUnit(
        id="bu-gh-wt",
        title="GH idea",
        one_liner="Test",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test",
        solution="Test",
        value_proposition="Test",
        evidence_signals=gh_ids[:8],  # 80% idea hit rate
    )
    store.insert_buildable_unit(unit)

    # High insight weight — should favor hackernews
    alloc_insight = compute_fetch_allocation(
        total_budget=60,
        adapter_names=["hackernews", "github"],
        store=store,
        insight_weight=0.9,
        idea_weight=0.1,
    )

    # High idea weight — should favor github
    alloc_idea = compute_fetch_allocation(
        total_budget=60,
        adapter_names=["hackernews", "github"],
        store=store,
        insight_weight=0.1,
        idea_weight=0.9,
    )

    assert alloc_insight["hackernews"] > alloc_idea["hackernews"]
    assert alloc_idea["github"] > alloc_insight["github"]


# ── 7. End-to-end feedback loop ─────────────────────────────────


def test_feedback_shifts_allocation_over_time(store: Store) -> None:
    """Simulate two 'pipeline runs' and verify feedback shifts allocation.

    Round 1: No feedback → roughly uniform.
    Round 2: After feedback, approved adapters get more budget.
    """
    # Round 1: cold start
    _insert_signals(store, "hackernews", 10)
    _insert_signals(store, "github", 10)

    alloc_round1 = compute_fetch_allocation(
        total_budget=60, adapter_names=["hackernews", "github"], store=store
    )
    # Both have same profile → similar allocation
    assert abs(alloc_round1["hackernews"] - alloc_round1["github"]) <= 5

    # Simulate pipeline producing ideas and user approving hackernews ideas
    hn_ids = [f"sig-hackernews-{i}" for i in range(10)]
    gh_ids = [f"sig-github-{i}" for i in range(10)]

    # hackernews: 3 approved ideas (triggers approval blending at >=3 feedback)
    for i in range(3):
        _insert_idea_with_feedback(
            store, "hackernews", f"bu-hn-loop-{i}", hn_ids[i : i + 1], "approved"
        )

    # github: 3 rejected ideas
    for i in range(3):
        _insert_idea_with_feedback(
            store, "github", f"bu-gh-loop-{i}", gh_ids[i : i + 1], "rejected"
        )

    # Round 2: with feedback
    alloc_round2 = compute_fetch_allocation(
        total_budget=60, adapter_names=["hackernews", "github"], store=store
    )

    # hackernews should now get more than github
    assert alloc_round2["hackernews"] > alloc_round2["github"]
    # The gap should be larger than in round 1
    gap_r1 = alloc_round1["hackernews"] - alloc_round1["github"]
    gap_r2 = alloc_round2["hackernews"] - alloc_round2["github"]
    assert gap_r2 > gap_r1
