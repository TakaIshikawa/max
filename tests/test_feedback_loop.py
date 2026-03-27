"""Tests for closed feedback loop — get_adapted_weights pure function."""

from __future__ import annotations

from max.evaluation.weights import DEFAULT_WEIGHTS, get_adapted_weights, get_weights


def test_no_feedback_returns_static():
    """No feedback → static profile, not adapted."""
    weights, adapted = get_adapted_weights("default", [])
    assert adapted is False
    assert weights == DEFAULT_WEIGHTS


def test_only_successes_returns_static():
    """All successes → no diversity → falls back to static."""
    outcomes = [
        {"dimension_values": {"pain_severity": 8, "build_effort": 6}, "success": True},
        {"dimension_values": {"pain_severity": 7, "build_effort": 5}, "success": True},
    ]
    weights, adapted = get_adapted_weights("default", outcomes)
    assert adapted is False


def test_only_failures_returns_static():
    """All failures → no diversity → falls back to static."""
    outcomes = [
        {"dimension_values": {"pain_severity": 3, "build_effort": 2}, "success": False},
        {"dimension_values": {"pain_severity": 4, "build_effort": 3}, "success": False},
    ]
    weights, adapted = get_adapted_weights("default", outcomes)
    assert adapted is False


def test_mixed_feedback_adapts():
    """Mix of successes and failures → weights adapted."""
    outcomes = [
        {"dimension_values": {"pain_severity": 9, "build_effort": 7, "composability": 8,
                              "addressable_scale": 7, "competitive_density": 8,
                              "timing_fit": 7, "compounding_value": 6}, "success": True},
        {"dimension_values": {"pain_severity": 3, "build_effort": 3, "composability": 4,
                              "addressable_scale": 4, "competitive_density": 5,
                              "timing_fit": 4, "compounding_value": 3}, "success": False},
    ]
    weights, adapted = get_adapted_weights("default", outcomes)
    assert adapted is True
    # Weights should still sum to ~1.0
    assert abs(sum(weights.values()) - 1.0) < 0.01
    # Dimensions where success scored higher should get boosted
    # pain_severity: 9 (success) vs 3 (failure) — big delta → weight up
    assert weights["pain_severity"] > DEFAULT_WEIGHTS["pain_severity"]


def test_adapted_weights_normalize():
    """Adapted weights always sum to 1.0."""
    outcomes = [
        {"dimension_values": {"pain_severity": 10, "build_effort": 10, "composability": 10,
                              "addressable_scale": 10, "competitive_density": 10,
                              "timing_fit": 10, "compounding_value": 10}, "success": True},
        {"dimension_values": {"pain_severity": 0, "build_effort": 0, "composability": 0,
                              "addressable_scale": 0, "competitive_density": 0,
                              "timing_fit": 0, "compounding_value": 0}, "success": False},
    ]
    weights, adapted = get_adapted_weights("default", outcomes)
    assert adapted is True
    assert abs(sum(weights.values()) - 1.0) < 0.01


def test_profile_respected():
    """Named profile is used as the base, not always default."""
    outcomes = []
    weights, adapted = get_adapted_weights("quick_wins", outcomes)
    assert adapted is False
    assert weights == get_weights("quick_wins")
    assert weights["build_effort"] == 0.30  # Quick wins profile emphasizes build_effort


def test_outcomes_missing_dimension_values_skipped():
    """Outcomes without dimension_values are filtered out."""
    outcomes = [
        {"buildable_unit_id": "bu-001", "success": True},  # no dimension_values
        {"buildable_unit_id": "bu-002", "success": False},  # no dimension_values
    ]
    weights, adapted = get_adapted_weights("default", outcomes)
    assert adapted is False  # No valid outcomes


def test_learning_rate_controls_magnitude():
    """Higher learning rate → bigger weight changes."""
    outcomes = [
        {"dimension_values": {"pain_severity": 9, "build_effort": 7, "composability": 8,
                              "addressable_scale": 7, "competitive_density": 8,
                              "timing_fit": 7, "compounding_value": 6}, "success": True},
        {"dimension_values": {"pain_severity": 3, "build_effort": 3, "composability": 4,
                              "addressable_scale": 4, "competitive_density": 5,
                              "timing_fit": 4, "compounding_value": 3}, "success": False},
    ]
    w_slow, _ = get_adapted_weights("default", outcomes, learning_rate=0.01)
    w_fast, _ = get_adapted_weights("default", outcomes, learning_rate=0.10)

    # Bigger learning rate → bigger deviation from default
    slow_delta = abs(w_slow["pain_severity"] - DEFAULT_WEIGHTS["pain_severity"])
    fast_delta = abs(w_fast["pain_severity"] - DEFAULT_WEIGHTS["pain_severity"])
    assert fast_delta > slow_delta
