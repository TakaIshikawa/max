"""Unit tests for adaptive fetch allocation with mocked Store.

These tests focus on edge cases and internal logic without requiring
a real Store or database. They mock get_adapter_quality_stats() and
get_adapter_approval_stats() to provide controlled test data.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from max.pipeline.fetch_strategy import compute_fetch_allocation


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def mock_store() -> MagicMock:
    """Create a mock Store with empty stats."""
    store = MagicMock()
    store.get_adapter_quality_stats.return_value = {}
    store.get_adapter_approval_stats.return_value = {}
    return store


# ── Edge cases: empty and minimal inputs ─────────────────────────


def test_empty_adapter_list_returns_empty_dict(mock_store: MagicMock) -> None:
    """Empty adapter_names should return empty dict."""
    result = compute_fetch_allocation(100, [], mock_store)
    assert result == {}


def test_single_adapter_gets_full_budget(mock_store: MagicMock) -> None:
    """Single adapter receives the entire budget."""
    result = compute_fetch_allocation(100, ["adapter_a"], mock_store)
    assert result == {"adapter_a": 100}


def test_single_adapter_with_quality_data(mock_store: MagicMock) -> None:
    """Single adapter with quality data still gets full budget."""
    mock_store.get_adapter_quality_stats.return_value = {
        "adapter_a": {
            "total_signals": 10,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.3,
        }
    }
    result = compute_fetch_allocation(50, ["adapter_a"], mock_store)
    assert result == {"adapter_a": 50}


# ── Budget constraints ───────────────────────────────────────────


def test_budget_less_than_min_sum_falls_back(mock_store: MagicMock) -> None:
    """When total_budget < min_per_adapter * n, distribute evenly."""
    adapters = ["a", "b", "c"]
    result = compute_fetch_allocation(6, adapters, mock_store, min_per_adapter=5)
    # 3 * 5 = 15 > 6, so each gets floor(6/3) = 2
    assert sum(result.values()) == 6
    assert all(v == 2 for v in result.values())


def test_budget_exactly_min_sum(mock_store: MagicMock) -> None:
    """When total_budget == min_per_adapter * n, each gets minimum."""
    adapters = ["a", "b", "c"]
    result = compute_fetch_allocation(15, adapters, mock_store, min_per_adapter=5)
    assert result == {"a": 5, "b": 5, "c": 5}


def test_budget_slightly_above_min_sum(mock_store: MagicMock) -> None:
    """Budget slightly above minimum gives best adapter the extra."""
    adapters = ["a", "b"]
    # With no quality data, all have quality=1.0, so first or arbitrary choice
    result = compute_fetch_allocation(11, adapters, mock_store, min_per_adapter=5)
    assert sum(result.values()) == 11
    # One adapter should get 6, the other 5
    assert set(result.values()) == {5, 6}


def test_minimum_floor_always_respected(mock_store: MagicMock) -> None:
    """Even low-quality adapters get at least min_per_adapter."""
    mock_store.get_adapter_quality_stats.return_value = {
        "good": {
            "total_signals": 10,
            "insight_hit_rate": 0.9,
            "idea_hit_rate": 0.9,
        },
        "bad": {
            "total_signals": 10,
            "insight_hit_rate": 0.0,
            "idea_hit_rate": 0.0,
        },
    }
    result = compute_fetch_allocation(
        30, ["good", "bad"], mock_store, min_per_adapter=5
    )
    assert result["bad"] >= 5
    assert result["good"] >= 5
    assert sum(result.values()) == 30


# ── Quality calculation with cold start ──────────────────────────


def test_cold_start_uniform_distribution(mock_store: MagicMock) -> None:
    """With no quality data, all adapters get roughly equal allocation."""
    adapters = ["a", "b", "c", "d"]
    result = compute_fetch_allocation(40, adapters, mock_store, min_per_adapter=3)
    # Should be uniform: each gets ~10
    assert sum(result.values()) == 40
    for v in result.values():
        assert 8 <= v <= 12


def test_insufficient_signals_defaults_to_quality_1(mock_store: MagicMock) -> None:
    """Adapter with < 5 signals gets default quality 1.0."""
    mock_store.get_adapter_quality_stats.return_value = {
        "new": {
            "total_signals": 3,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
        "established": {
            "total_signals": 10,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
    }
    result = compute_fetch_allocation(30, ["new", "established"], mock_store)
    # Both should get similar allocation (new treated as quality=1.0)
    assert sum(result.values()) == 30
    # With smoothing=0.3, new (quality=1.0) might get slightly more than established (quality=0.52)
    # but they should be relatively close
    assert abs(result["new"] - result["established"]) <= 5


def test_all_adapters_zero_quality_fallback(mock_store: MagicMock) -> None:
    """When all adapters have zero quality, max_q falls back to 1.0."""
    mock_store.get_adapter_quality_stats.return_value = {
        "a": {
            "total_signals": 10,
            "insight_hit_rate": 0.0,
            "idea_hit_rate": 0.0,
        },
        "b": {
            "total_signals": 10,
            "insight_hit_rate": 0.0,
            "idea_hit_rate": 0.0,
        },
    }
    result = compute_fetch_allocation(30, ["a", "b"], mock_store)
    # Should still work without division by zero
    assert sum(result.values()) == 30
    # Should be roughly equal
    assert abs(result["a"] - result["b"]) <= 2


# ── Quality-based allocation ─────────────────────────────────────


def test_high_quality_adapter_gets_larger_share(mock_store: MagicMock) -> None:
    """Adapter with higher quality scores gets more allocation."""
    mock_store.get_adapter_quality_stats.return_value = {
        "good": {
            "total_signals": 10,
            "insight_hit_rate": 0.8,
            "idea_hit_rate": 0.7,
        },
        "bad": {
            "total_signals": 10,
            "insight_hit_rate": 0.1,
            "idea_hit_rate": 0.1,
        },
    }
    result = compute_fetch_allocation(
        30, ["good", "bad"], mock_store, min_per_adapter=3
    )
    assert result["good"] > result["bad"]
    assert sum(result.values()) == 30


def test_insight_weight_parameter_respected(mock_store: MagicMock) -> None:
    """insight_weight parameter affects quality calculation."""
    mock_store.get_adapter_quality_stats.return_value = {
        "insight_heavy": {
            "total_signals": 10,
            "insight_hit_rate": 0.9,
            "idea_hit_rate": 0.1,
        },
        "idea_heavy": {
            "total_signals": 10,
            "insight_hit_rate": 0.1,
            "idea_hit_rate": 0.9,
        },
    }
    # High insight weight should favor insight_heavy
    result = compute_fetch_allocation(
        30,
        ["insight_heavy", "idea_heavy"],
        mock_store,
        insight_weight=0.9,
        idea_weight=0.1,
    )
    assert result["insight_heavy"] > result["idea_heavy"]


def test_idea_weight_parameter_respected(mock_store: MagicMock) -> None:
    """idea_weight parameter affects quality calculation."""
    mock_store.get_adapter_quality_stats.return_value = {
        "insight_heavy": {
            "total_signals": 10,
            "insight_hit_rate": 0.9,
            "idea_hit_rate": 0.1,
        },
        "idea_heavy": {
            "total_signals": 10,
            "insight_hit_rate": 0.1,
            "idea_hit_rate": 0.9,
        },
    }
    # High idea weight should favor idea_heavy
    result = compute_fetch_allocation(
        30,
        ["insight_heavy", "idea_heavy"],
        mock_store,
        insight_weight=0.1,
        idea_weight=0.9,
    )
    assert result["idea_heavy"] > result["insight_heavy"]


# ── Approval-aware quality ───────────────────────────────────────


def test_approval_blending_with_sufficient_feedback(mock_store: MagicMock) -> None:
    """With >= 3 feedbacked units, approval_rate is blended into quality."""
    mock_store.get_adapter_quality_stats.return_value = {
        "approved": {
            "total_signals": 10,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
        "rejected": {
            "total_signals": 10,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
    }
    mock_store.get_adapter_approval_stats.return_value = {
        "approved": {
            "total_feedbacked": 5,
            "approval_rate": 1.0,
        },
        "rejected": {
            "total_feedbacked": 5,
            "approval_rate": 0.0,
        },
    }
    result = compute_fetch_allocation(
        30, ["approved", "rejected"], mock_store, min_per_adapter=3
    )
    # approved should get significantly more due to 100% approval rate
    assert result["approved"] > result["rejected"]
    assert sum(result.values()) == 30


def test_approval_ignored_with_insufficient_feedback(mock_store: MagicMock) -> None:
    """With < 3 feedbacked units, approval_rate is not used."""
    mock_store.get_adapter_quality_stats.return_value = {
        "a": {
            "total_signals": 10,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
        "b": {
            "total_signals": 10,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
    }
    mock_store.get_adapter_approval_stats.return_value = {
        "a": {
            "total_feedbacked": 2,
            "approval_rate": 1.0,
        },
        "b": {
            "total_feedbacked": 2,
            "approval_rate": 0.0,
        },
    }
    result = compute_fetch_allocation(30, ["a", "b"], mock_store)
    # Should be roughly equal since approval not used (< 3 feedback)
    assert sum(result.values()) == 30
    assert abs(result["a"] - result["b"]) <= 3


def test_mixed_feedback_thresholds(mock_store: MagicMock) -> None:
    """One adapter with sufficient feedback, one without."""
    mock_store.get_adapter_quality_stats.return_value = {
        "mature": {
            "total_signals": 10,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
        "new": {
            "total_signals": 10,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
    }
    mock_store.get_adapter_approval_stats.return_value = {
        "mature": {
            "total_feedbacked": 5,
            "approval_rate": 0.9,
        },
        "new": {
            "total_feedbacked": 1,
            "approval_rate": 0.5,
        },
    }
    result = compute_fetch_allocation(30, ["mature", "new"], mock_store)
    # mature should get more due to high approval rate being factored in
    assert result["mature"] > result["new"]
    assert sum(result.values()) == 30


# ── Smoothing parameter ──────────────────────────────────────────


def test_smoothing_zero_pure_quality_based(mock_store: MagicMock) -> None:
    """smoothing=0.0 gives pure quality-based allocation."""
    mock_store.get_adapter_quality_stats.return_value = {
        "excellent": {
            "total_signals": 10,
            "insight_hit_rate": 1.0,
            "idea_hit_rate": 1.0,
        },
        "poor": {
            "total_signals": 10,
            "insight_hit_rate": 0.0,
            "idea_hit_rate": 0.0,
        },
    }
    result = compute_fetch_allocation(
        30, ["excellent", "poor"], mock_store, min_per_adapter=3, smoothing=0.0
    )
    # With zero smoothing, excellent should get much more
    assert result["excellent"] > result["poor"] + 5
    assert sum(result.values()) == 30


def test_smoothing_one_pure_uniform(mock_store: MagicMock) -> None:
    """smoothing=1.0 gives pure uniform allocation."""
    mock_store.get_adapter_quality_stats.return_value = {
        "excellent": {
            "total_signals": 10,
            "insight_hit_rate": 1.0,
            "idea_hit_rate": 1.0,
        },
        "poor": {
            "total_signals": 10,
            "insight_hit_rate": 0.0,
            "idea_hit_rate": 0.0,
        },
    }
    result = compute_fetch_allocation(
        30, ["excellent", "poor"], mock_store, min_per_adapter=3, smoothing=1.0
    )
    # With full smoothing, should be equal
    assert result["excellent"] == result["poor"]
    assert sum(result.values()) == 30


def test_smoothing_intermediate(mock_store: MagicMock) -> None:
    """Intermediate smoothing values blend quality and uniform."""
    mock_store.get_adapter_quality_stats.return_value = {
        "good": {
            "total_signals": 10,
            "insight_hit_rate": 0.8,
            "idea_hit_rate": 0.8,
        },
        "bad": {
            "total_signals": 10,
            "insight_hit_rate": 0.2,
            "idea_hit_rate": 0.2,
        },
    }
    # Test with different smoothing values
    result_low = compute_fetch_allocation(
        30, ["good", "bad"], mock_store, smoothing=0.2
    )
    result_high = compute_fetch_allocation(
        30, ["good", "bad"], mock_store, smoothing=0.8
    )

    # Lower smoothing should give good adapter more
    assert result_low["good"] > result_high["good"]
    assert result_high["bad"] > result_low["bad"]


# ── Total budget reconciliation ──────────────────────────────────


def test_total_always_matches_budget(mock_store: MagicMock) -> None:
    """Sum of allocations always equals total_budget exactly."""
    mock_store.get_adapter_quality_stats.return_value = {
        "a": {"total_signals": 10, "insight_hit_rate": 0.7, "idea_hit_rate": 0.6},
        "b": {"total_signals": 10, "insight_hit_rate": 0.5, "idea_hit_rate": 0.4},
        "c": {"total_signals": 10, "insight_hit_rate": 0.3, "idea_hit_rate": 0.2},
    }

    # Test with various odd budgets that require rounding adjustments
    for budget in [37, 41, 53, 97, 101]:
        result = compute_fetch_allocation(budget, ["a", "b", "c"], mock_store)
        assert sum(result.values()) == budget, f"Failed for budget={budget}"


def test_rounding_adjustment_goes_to_best_adapter(mock_store: MagicMock) -> None:
    """Rounding differences are absorbed by highest-quality adapter."""
    mock_store.get_adapter_quality_stats.return_value = {
        "best": {
            "total_signals": 10,
            "insight_hit_rate": 0.9,
            "idea_hit_rate": 0.9,
        },
        "middle": {
            "total_signals": 10,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
        "worst": {
            "total_signals": 10,
            "insight_hit_rate": 0.1,
            "idea_hit_rate": 0.1,
        },
    }

    result = compute_fetch_allocation(
        37, ["best", "middle", "worst"], mock_store, min_per_adapter=3
    )

    assert sum(result.values()) == 37
    # best should have the most (including rounding adjustment)
    assert result["best"] > result["middle"]
    assert result["middle"] > result["worst"]


# ── Multiple adapters with varied profiles ──────────────────────


def test_three_adapters_with_gradient_quality(mock_store: MagicMock) -> None:
    """Three adapters with low/medium/high quality get proportional allocation."""
    mock_store.get_adapter_quality_stats.return_value = {
        "high": {
            "total_signals": 10,
            "insight_hit_rate": 0.8,
            "idea_hit_rate": 0.8,
        },
        "medium": {
            "total_signals": 10,
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
        "low": {
            "total_signals": 10,
            "insight_hit_rate": 0.2,
            "idea_hit_rate": 0.2,
        },
    }
    result = compute_fetch_allocation(
        60, ["high", "medium", "low"], mock_store, min_per_adapter=5
    )

    assert sum(result.values()) == 60
    assert result["high"] > result["medium"] > result["low"]
    assert all(v >= 5 for v in result.values())


def test_four_adapters_mixed_data_availability(mock_store: MagicMock) -> None:
    """Mix of adapters: some with data, some cold start."""
    mock_store.get_adapter_quality_stats.return_value = {
        "established": {
            "total_signals": 20,
            "insight_hit_rate": 0.7,
            "idea_hit_rate": 0.6,
        },
        "new": {
            "total_signals": 2,  # < 5, defaults to quality 1.0
            "insight_hit_rate": 0.5,
            "idea_hit_rate": 0.5,
        },
        # "cold" has no stats at all
    }

    result = compute_fetch_allocation(
        40, ["established", "new", "cold", "unknown"], mock_store
    )

    assert sum(result.values()) == 40
    assert set(result.keys()) == {"established", "new", "cold", "unknown"}
    # established has quality = 0.4*0.7 + 0.6*0.6 = 0.64
    # new/cold/unknown have quality = 1.0
    # With smoothing, cold-start adapters might actually get slightly more
    # The key test is that allocation works without errors
    assert all(v >= 3 for v in result.values())  # min_per_adapter default is 3


# ── Edge case: extreme quality differences ──────────────────────


def test_extreme_quality_difference_respects_min(mock_store: MagicMock) -> None:
    """Even with extreme quality difference, min_per_adapter is respected."""
    mock_store.get_adapter_quality_stats.return_value = {
        "perfect": {
            "total_signals": 100,
            "insight_hit_rate": 1.0,
            "idea_hit_rate": 1.0,
        },
        "zero": {
            "total_signals": 100,
            "insight_hit_rate": 0.0,
            "idea_hit_rate": 0.0,
        },
    }
    mock_store.get_adapter_approval_stats.return_value = {
        "perfect": {
            "total_feedbacked": 10,
            "approval_rate": 1.0,
        },
        "zero": {
            "total_feedbacked": 10,
            "approval_rate": 0.0,
        },
    }

    result = compute_fetch_allocation(
        100, ["perfect", "zero"], mock_store, min_per_adapter=10
    )

    assert result["zero"] >= 10
    assert result["perfect"] >= 10
    assert sum(result.values()) == 100


# ── Parameter validation edge cases ──────────────────────────────


def test_zero_total_budget(mock_store: MagicMock) -> None:
    """Zero budget falls back to max(total_budget // n, 1) = 1 per adapter."""
    result = compute_fetch_allocation(0, ["a", "b"], mock_store)
    # Implementation: per = max(total_budget // n, 1) = max(0, 1) = 1
    assert sum(result.values()) == 2
    assert all(v == 1 for v in result.values())


def test_zero_min_per_adapter(mock_store: MagicMock) -> None:
    """min_per_adapter=0 should still work."""
    mock_store.get_adapter_quality_stats.return_value = {
        "good": {
            "total_signals": 10,
            "insight_hit_rate": 0.9,
            "idea_hit_rate": 0.9,
        },
        "bad": {
            "total_signals": 10,
            "insight_hit_rate": 0.1,
            "idea_hit_rate": 0.1,
        },
    }
    result = compute_fetch_allocation(
        20, ["good", "bad"], mock_store, min_per_adapter=0
    )

    assert sum(result.values()) == 20
    # good should get significantly more
    assert result["good"] > result["bad"]


def test_large_adapter_list(mock_store: MagicMock) -> None:
    """Many adapters should still work correctly."""
    adapters = [f"adapter_{i}" for i in range(20)]
    result = compute_fetch_allocation(200, adapters, mock_store, min_per_adapter=3)

    assert set(result.keys()) == set(adapters)
    assert sum(result.values()) == 200
    assert all(v >= 3 for v in result.values())
