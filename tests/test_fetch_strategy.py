"""Tests for adaptive fetch allocation."""

from __future__ import annotations

from max.pipeline.fetch_strategy import compute_fetch_allocation
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


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


def _seed_adapter_data(
    store: Store,
    adapter: str,
    signal_count: int,
    *,
    insight_refs: list[str] | None = None,
    idea_refs: list[str] | None = None,
) -> list[str]:
    """Seed signals for an adapter and optionally reference them in insights/ideas."""
    sig_ids = []
    for i in range(signal_count):
        sig_id = f"sig-{adapter}-{i}"
        sig = _make_signal(adapter, sig_id)
        store.insert_signal(sig)
        sig_ids.append(sig_id)

    if insight_refs:
        ins = Insight(
            id=f"ins-{adapter}",
            category=InsightCategory.GAP,
            title=f"Insight from {adapter}",
            summary="Test insight",
            evidence=insight_refs,
            confidence=0.8,
            domains=["test"],
        )
        store.insert_insight(ins)

    if idea_refs:
        unit = BuildableUnit(
            id=f"bu-{adapter}",
            title=f"Idea from {adapter}",
            one_liner="Test idea",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Test problem",
            solution="Test solution",
            value_proposition="Test value",
            evidence_signals=idea_refs,
        )
        store.insert_buildable_unit(unit)

    return sig_ids


# ── Cold start / uniform ─────────────────────────────────────────


def test_cold_start_even_distribution(store: Store) -> None:
    """With no historical data, all adapters get roughly equal allocation."""
    adapters = ["hackernews", "reddit", "github"]
    allocation = compute_fetch_allocation(30, adapters, store)
    assert set(allocation.keys()) == set(adapters)
    assert sum(allocation.values()) == 30
    # Should be roughly uniform
    for v in allocation.values():
        assert 8 <= v <= 12


def test_empty_adapters_returns_empty(store: Store) -> None:
    assert compute_fetch_allocation(30, [], store) == {}


# ── Quality-based allocation ─────────────────────────────────────


def test_high_quality_adapter_gets_larger_share(store: Store) -> None:
    """Adapter with signals referenced in insights/ideas should get more budget."""
    # Adapter A: 10 signals, 5 referenced in insights, 5 in ideas (high quality)
    a_ids = _seed_adapter_data(store, "adapter_a", 10)
    _seed_adapter_data(
        store, "adapter_a_insights", 0,
        insight_refs=a_ids[:5],
    )
    # Actually, we need insights referencing adapter_a's signals directly
    ins = Insight(
        id="ins-quality-a",
        category=InsightCategory.GAP,
        title="Quality insight",
        summary="Test",
        evidence=a_ids[:5],
        confidence=0.8,
        domains=["test"],
    )
    store.insert_insight(ins)
    unit = BuildableUnit(
        id="bu-quality-a",
        title="Quality idea",
        one_liner="Test",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test",
        solution="Test",
        value_proposition="Test",
        evidence_signals=a_ids[:5],
    )
    store.insert_buildable_unit(unit)

    # Adapter B: 10 signals, none referenced (low quality)
    _seed_adapter_data(store, "adapter_b", 10)

    allocation = compute_fetch_allocation(
        30, ["adapter_a", "adapter_b"], store,
    )
    assert allocation["adapter_a"] > allocation["adapter_b"]


# ── Minimum floor ────────────────────────────────────────────────


def test_minimum_floor_respected(store: Store) -> None:
    """Each adapter should get at least min_per_adapter signals."""
    adapters = ["a", "b", "c"]
    allocation = compute_fetch_allocation(
        30, adapters, store, min_per_adapter=5,
    )
    for v in allocation.values():
        assert v >= 5


def test_budget_too_small_for_minimums(store: Store) -> None:
    """When total budget < min_per_adapter * n, split evenly."""
    adapters = ["a", "b", "c"]
    allocation = compute_fetch_allocation(
        6, adapters, store, min_per_adapter=5,
    )
    assert sum(allocation.values()) == 6
    for v in allocation.values():
        assert v == 2


# ── Total budget exactness ───────────────────────────────────────


def test_total_budget_exact(store: Store) -> None:
    """Sum of allocations should equal total_budget."""
    adapters = ["a", "b", "c", "d"]
    allocation = compute_fetch_allocation(37, adapters, store)
    assert sum(allocation.values()) == 37


# ── Smoothing parameter ─────────────────────────────────────────


def test_smoothing_1_gives_uniform(store: Store) -> None:
    """smoothing=1.0 should give uniform distribution."""
    _seed_adapter_data(store, "good", 10)
    _seed_adapter_data(store, "bad", 10)

    allocation = compute_fetch_allocation(
        30, ["good", "bad"], store, smoothing=1.0,
    )
    # With full smoothing, allocations should be equal
    assert allocation["good"] == allocation["bad"]


# ── Single adapter edge case ─────────────────────────────────────


def test_single_adapter_gets_full_budget(store: Store) -> None:
    allocation = compute_fetch_allocation(30, ["only"], store)
    assert allocation["only"] == 30


# ── get_adapter_quality_stats ────────────────────────────────────


def test_adapter_quality_stats_empty(store: Store) -> None:
    stats = store.get_adapter_quality_stats()
    assert stats == {}


def test_adapter_quality_stats_with_data(store: Store) -> None:
    sig_ids = _seed_adapter_data(store, "test_adapter", 10)

    ins = Insight(
        id="ins-stats",
        category=InsightCategory.GAP,
        title="Test",
        summary="Test",
        evidence=sig_ids[:3],
        confidence=0.8,
        domains=["test"],
    )
    store.insert_insight(ins)

    stats = store.get_adapter_quality_stats()
    assert "test_adapter" in stats
    assert stats["test_adapter"]["total_signals"] == 10
    assert stats["test_adapter"]["insight_hit_rate"] == 0.3  # 3/10
    assert stats["test_adapter"]["idea_hit_rate"] == 0.0
