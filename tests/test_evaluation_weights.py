"""Tests for evaluation weight computation."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest

from max.evaluation.weights import (
    DEFAULT_WEIGHTS,
    INVERTED_DIMENSIONS,
    WEIGHT_PROFILES,
    adapt_weights,
    compute_overall_score,
    get_adapted_weights,
    get_weights,
    load_weights,
    save_weights,
)


# ============================================================================
# 1. Weight Profile Invariants
# ============================================================================


def test_default_weights_sum_to_one() -> None:
    """DEFAULT_WEIGHTS should sum to 1.0."""
    total = sum(DEFAULT_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001


def test_default_weights_has_seven_dimensions() -> None:
    """DEFAULT_WEIGHTS should have exactly 7 dimensions."""
    assert len(DEFAULT_WEIGHTS) == 7
    expected_dims = {
        "pain_severity",
        "addressable_scale",
        "build_effort",
        "composability",
        "competitive_density",
        "timing_fit",
        "compounding_value",
    }
    assert set(DEFAULT_WEIGHTS.keys()) == expected_dims


def test_all_profiles_sum_to_one() -> None:
    """All weight profiles should sum to 1.0."""
    for profile_name, weights in WEIGHT_PROFILES.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001, f"Profile {profile_name} sums to {total}"


def test_all_profiles_have_seven_dimensions() -> None:
    """All weight profiles should have exactly 7 dimensions matching DEFAULT_WEIGHTS."""
    expected_keys = set(DEFAULT_WEIGHTS.keys())
    for profile_name, weights in WEIGHT_PROFILES.items():
        assert len(weights) == 7, f"Profile {profile_name} has {len(weights)} dimensions"
        assert set(weights.keys()) == expected_keys, f"Profile {profile_name} has mismatched keys"


def test_get_weights_default() -> None:
    """get_weights('default') should return DEFAULT_WEIGHTS."""
    assert get_weights("default") == DEFAULT_WEIGHTS


def test_get_weights_unknown_fallback() -> None:
    """get_weights with unknown profile should fall back to DEFAULT_WEIGHTS."""
    assert get_weights("unknown_profile_xyz") == DEFAULT_WEIGHTS
    assert get_weights("") == DEFAULT_WEIGHTS


def test_quick_wins_profile_emphasizes_build_effort() -> None:
    """quick_wins profile should heavily favor build_effort (0.30)."""
    weights = get_weights("quick_wins")
    assert weights["build_effort"] == 0.30
    # Should be the highest weighted dimension
    assert all(weights["build_effort"] >= w for w in weights.values())


def test_moonshots_profile_emphasizes_compounding_value() -> None:
    """moonshots profile should favor compounding_value and pain_severity."""
    weights = get_weights("moonshots")
    assert weights["compounding_value"] == 0.20
    assert weights["pain_severity"] == 0.25
    assert weights["build_effort"] == 0.05  # Low penalty for effort


def test_ecosystem_profile_emphasizes_composability() -> None:
    """ecosystem profile should heavily favor composability (0.30)."""
    weights = get_weights("ecosystem")
    assert weights["composability"] == 0.30
    # Should be the highest weighted dimension
    assert all(weights["composability"] >= w for w in weights.values())


def test_agent_first_profile_balance() -> None:
    """agent_first profile should balance addressable_scale and composability."""
    weights = get_weights("agent_first")
    assert weights["addressable_scale"] == 0.20
    assert weights["composability"] == 0.20
    assert weights["competitive_density"] == 0.05  # Lower concern


# ============================================================================
# 2. compute_overall_score
# ============================================================================


def test_compute_overall_score_perfect() -> None:
    """All dimensions at 10.0 should yield 100.0."""
    values = {dim: 10.0 for dim in DEFAULT_WEIGHTS}
    score = compute_overall_score(values)
    assert score == 100.0


def test_compute_overall_score_zero() -> None:
    """All dimensions at 0.0 should yield 0.0."""
    values = {dim: 0.0 for dim in DEFAULT_WEIGHTS}
    score = compute_overall_score(values)
    assert score == 0.0


def test_compute_overall_score_mid() -> None:
    """All dimensions at 5.0 should yield 50.0."""
    values = {dim: 5.0 for dim in DEFAULT_WEIGHTS}
    score = compute_overall_score(values)
    assert score == 50.0


def test_compute_overall_score_weighted() -> None:
    """Only pain_severity at max (weight=0.20) should yield 20.0."""
    values = {dim: 0.0 for dim in DEFAULT_WEIGHTS}
    values["pain_severity"] = 10.0
    score = compute_overall_score(values)
    # 10 * 0.20 * 10 = 20.0
    assert score == 20.0


def test_compute_overall_score_specific_calculation() -> None:
    """Verify specific calculation with mixed values."""
    values = {
        "pain_severity": 8.0,
        "addressable_scale": 6.0,
        "build_effort": 7.0,
        "composability": 5.0,
        "competitive_density": 4.0,
        "timing_fit": 9.0,
        "compounding_value": 3.0,
    }
    # Expected: (8*0.20 + 6*0.15 + 7*0.15 + 5*0.15 + 4*0.10 + 9*0.10 + 3*0.15) * 10
    # = (1.6 + 0.9 + 1.05 + 0.75 + 0.4 + 0.9 + 0.45) * 10
    # = 6.05 * 10 = 60.5
    score = compute_overall_score(values)
    assert score == pytest.approx(60.5, abs=0.01)


def test_compute_overall_score_custom_weights() -> None:
    """Custom weights should be respected."""
    values = {"pain_severity": 10.0}
    custom = {"pain_severity": 1.0}
    score = compute_overall_score(values, weights=custom)
    assert score == 100.0


def test_compute_overall_score_custom_weights_multiple_dims() -> None:
    """Custom weights with multiple dimensions."""
    values = {
        "dim_a": 5.0,
        "dim_b": 8.0,
    }
    custom = {
        "dim_a": 0.3,
        "dim_b": 0.7,
    }
    # (5 * 0.3 + 8 * 0.7) * 10 = (1.5 + 5.6) * 10 = 71.0
    score = compute_overall_score(values, weights=custom)
    assert score == pytest.approx(71.0, abs=0.01)


def test_compute_overall_score_missing_dimensions() -> None:
    """Missing dimensions should be treated as 0."""
    values = {
        "pain_severity": 8.0,
        # Other dimensions missing
    }
    score = compute_overall_score(values)
    # Only pain_severity contributes: 8 * 0.20 * 10 = 16.0
    assert score == pytest.approx(16.0, abs=0.01)


def test_compute_overall_score_none_weights() -> None:
    """None weights should use DEFAULT_WEIGHTS."""
    values = {dim: 5.0 for dim in DEFAULT_WEIGHTS}
    score = compute_overall_score(values, weights=None)
    assert score == 50.0


def test_compute_overall_score_extra_dimensions_ignored() -> None:
    """Extra dimensions not in weights should be ignored."""
    values = {dim: 5.0 for dim in DEFAULT_WEIGHTS}
    values["unknown_dimension"] = 10.0
    score = compute_overall_score(values)
    assert score == 50.0  # Unknown dimension doesn't affect score


def test_compute_overall_score_inverted_dimension_does_not_affect_compute() -> None:
    """Inverted dimensions are NOT inverted in compute_overall_score.

    Note: The INVERTED_DIMENSIONS constant documents which dimensions are
    semantically inverted (lower is better), but compute_overall_score takes
    raw dimension values as-is. Inversion happens at the LLM scoring stage,
    not in the mathematical computation.
    """
    # Set an inverted dimension (build_effort) to high value
    values = {dim: 0.0 for dim in DEFAULT_WEIGHTS}
    values["build_effort"] = 10.0
    score = compute_overall_score(values)

    # build_effort weight is 0.15, so: 10 * 0.15 * 10 = 15.0
    assert score == pytest.approx(15.0, abs=0.01)

    # Setting competitive_density (also inverted) to high value
    values = {dim: 0.0 for dim in DEFAULT_WEIGHTS}
    values["competitive_density"] = 10.0
    score = compute_overall_score(values)

    # competitive_density weight is 0.10, so: 10 * 0.10 * 10 = 10.0
    assert score == pytest.approx(10.0, abs=0.01)


def test_compute_overall_score_empty_dict() -> None:
    """Empty dimension values should yield 0.0."""
    values: dict[str, float] = {}
    score = compute_overall_score(values)
    assert score == 0.0


def test_compute_overall_score_nan_values() -> None:
    """NaN values should be handled (treated as contributing NaN to sum)."""
    values = {dim: 5.0 for dim in DEFAULT_WEIGHTS}
    values["pain_severity"] = float("nan")
    score = compute_overall_score(values)
    # Score will be NaN due to NaN in calculation
    assert math.isnan(score)


def test_compute_overall_score_infinity_values() -> None:
    """Infinity values should be handled (produce infinite score)."""
    values = {dim: 5.0 for dim in DEFAULT_WEIGHTS}
    values["pain_severity"] = float("inf")
    score = compute_overall_score(values)
    # Score will be infinity
    assert math.isinf(score)


def test_compute_overall_score_property_based_range() -> None:
    """Property test: scores should always be in [0.0, 100.0] for valid inputs.

    Tests 100 random combinations of dimension values in [0, 10] range.
    """
    random.seed(42)  # Reproducible

    for _ in range(100):
        # Generate random values in [0, 10] for each dimension
        values = {dim: random.uniform(0, 10) for dim in DEFAULT_WEIGHTS}
        score = compute_overall_score(values)

        # Score should be in valid range
        assert 0.0 <= score <= 100.0, f"Score {score} out of range for values {values}"


def test_compute_overall_score_property_based_boundary() -> None:
    """Property test: boundary values (0, 10) should produce valid scores."""
    random.seed(42)

    for _ in range(50):
        # Generate random values using only boundary values (0 or 10)
        values = {dim: random.choice([0.0, 10.0]) for dim in DEFAULT_WEIGHTS}
        score = compute_overall_score(values)

        assert 0.0 <= score <= 100.0, f"Score {score} out of range for values {values}"
        assert not math.isnan(score), f"Score is NaN for values {values}"


# ============================================================================
# 3. adapt_weights
# ============================================================================


def test_adapt_weights_empty_outcomes() -> None:
    """Empty outcomes should return base unchanged."""
    base = DEFAULT_WEIGHTS.copy()
    result = adapt_weights([])
    assert result == base


def test_adapt_weights_all_successes() -> None:
    """All successes (no failures) should return base unchanged."""
    outcomes = [
        {
            "dimension_values": {dim: 8.0 for dim in DEFAULT_WEIGHTS},
            "success": True,
        },
        {
            "dimension_values": {dim: 7.0 for dim in DEFAULT_WEIGHTS},
            "success": True,
        },
    ]
    base = DEFAULT_WEIGHTS.copy()
    result = adapt_weights(outcomes)
    assert result == base


def test_adapt_weights_all_failures() -> None:
    """All failures (no successes) should return base unchanged."""
    outcomes = [
        {
            "dimension_values": {dim: 3.0 for dim in DEFAULT_WEIGHTS},
            "success": False,
        },
        {
            "dimension_values": {dim: 2.0 for dim in DEFAULT_WEIGHTS},
            "success": False,
        },
    ]
    base = DEFAULT_WEIGHTS.copy()
    result = adapt_weights(outcomes)
    assert result == base


def test_adapt_weights_mixed_outcomes() -> None:
    """Mixed outcomes should shift weights toward dimensions correlated with success."""
    outcomes = [
        # Success with high pain_severity
        {
            "dimension_values": {
                "pain_severity": 9.0,
                "addressable_scale": 5.0,
                "build_effort": 5.0,
                "composability": 5.0,
                "competitive_density": 5.0,
                "timing_fit": 5.0,
                "compounding_value": 5.0,
            },
            "success": True,
        },
        # Failure with low pain_severity
        {
            "dimension_values": {
                "pain_severity": 2.0,
                "addressable_scale": 5.0,
                "build_effort": 5.0,
                "composability": 5.0,
                "competitive_density": 5.0,
                "timing_fit": 5.0,
                "compounding_value": 5.0,
            },
            "success": False,
        },
    ]
    result = adapt_weights(outcomes)
    # pain_severity should increase (correlates with success)
    assert result["pain_severity"] > DEFAULT_WEIGHTS["pain_severity"]


def test_adapt_weights_sum_to_one() -> None:
    """Adapted weights should always sum to 1.0."""
    outcomes = [
        {
            "dimension_values": {dim: 8.0 for dim in DEFAULT_WEIGHTS},
            "success": True,
        },
        {
            "dimension_values": {dim: 3.0 for dim in DEFAULT_WEIGHTS},
            "success": False,
        },
    ]
    result = adapt_weights(outcomes)
    total = sum(result.values())
    assert abs(total - 1.0) < 0.001


def test_adapt_weights_minimum_threshold() -> None:
    """Weights are floored at 0.01 before renormalization."""
    # Create outcomes that strongly favor one dimension
    outcomes = [
        {
            "dimension_values": {
                "pain_severity": 10.0,
                "addressable_scale": 0.0,
                "build_effort": 0.0,
                "composability": 0.0,
                "competitive_density": 0.0,
                "timing_fit": 0.0,
                "compounding_value": 0.0,
            },
            "success": True,
        },
        {
            "dimension_values": {
                "pain_severity": 0.0,
                "addressable_scale": 10.0,
                "build_effort": 10.0,
                "composability": 10.0,
                "competitive_density": 10.0,
                "timing_fit": 10.0,
                "compounding_value": 10.0,
            },
            "success": False,
        },
    ]
    result = adapt_weights(outcomes, learning_rate=0.5)
    # All weights should be positive (floor is applied before renormalization)
    assert all(w > 0 for w in result.values())
    # The dimension correlated with success should have higher weight
    assert result["pain_severity"] > 0.5


def test_adapt_weights_learning_rate_affects_magnitude() -> None:
    """Higher learning_rate should produce larger adjustments."""
    outcomes = [
        {
            "dimension_values": {
                "pain_severity": 9.0,
                "addressable_scale": 5.0,
                "build_effort": 5.0,
                "composability": 5.0,
                "competitive_density": 5.0,
                "timing_fit": 5.0,
                "compounding_value": 5.0,
            },
            "success": True,
        },
        {
            "dimension_values": {
                "pain_severity": 2.0,
                "addressable_scale": 5.0,
                "build_effort": 5.0,
                "composability": 5.0,
                "competitive_density": 5.0,
                "timing_fit": 5.0,
                "compounding_value": 5.0,
            },
            "success": False,
        },
    ]

    result_low = adapt_weights(outcomes, learning_rate=0.01)
    result_high = adapt_weights(outcomes, learning_rate=0.10)

    # High learning rate should produce larger change in pain_severity
    change_low = abs(result_low["pain_severity"] - DEFAULT_WEIGHTS["pain_severity"])
    change_high = abs(result_high["pain_severity"] - DEFAULT_WEIGHTS["pain_severity"])
    assert change_high > change_low


def test_adapt_weights_with_custom_base() -> None:
    """adapt_weights should accept custom base weights."""
    custom_base = {
        "pain_severity": 0.5,
        "addressable_scale": 0.5,
    }
    outcomes = [
        {
            "dimension_values": {
                "pain_severity": 10.0,
                "addressable_scale": 0.0,
            },
            "success": True,
        },
        {
            "dimension_values": {
                "pain_severity": 0.0,
                "addressable_scale": 10.0,
            },
            "success": False,
        },
    ]
    result = adapt_weights(outcomes, base_weights=custom_base)
    # Should work with custom base
    assert "pain_severity" in result
    assert "addressable_scale" in result
    # Should still sum to 1.0
    assert abs(sum(result.values()) - 1.0) < 0.001


def test_adapt_weights_missing_dimension_values() -> None:
    """Missing dimensions in outcomes should be treated as 0."""
    outcomes = [
        {
            "dimension_values": {
                "pain_severity": 10.0,
                # Other dimensions missing
            },
            "success": True,
        },
        {
            "dimension_values": {
                "pain_severity": 0.0,
            },
            "success": False,
        },
    ]
    result = adapt_weights(outcomes)
    # Should not crash, should return valid weights
    assert len(result) == 7
    assert abs(sum(result.values()) - 1.0) < 0.001


def test_adapt_weights_no_weight_exceeds_one() -> None:
    """No individual weight should exceed 1.0 after adaptation."""
    # Create extreme outcomes to try to push one weight very high
    outcomes = [
        {
            "dimension_values": {
                "pain_severity": 10.0,
                "addressable_scale": 0.0,
                "build_effort": 0.0,
                "composability": 0.0,
                "competitive_density": 0.0,
                "timing_fit": 0.0,
                "compounding_value": 0.0,
            },
            "success": True,
        },
        {
            "dimension_values": {
                "pain_severity": 0.0,
                "addressable_scale": 10.0,
                "build_effort": 10.0,
                "composability": 10.0,
                "competitive_density": 10.0,
                "timing_fit": 10.0,
                "compounding_value": 10.0,
            },
            "success": False,
        },
    ]

    # Try with high learning rate
    result = adapt_weights(outcomes, learning_rate=0.5)

    # No weight should exceed 1.0
    for dim, weight in result.items():
        assert weight <= 1.0, f"{dim} weight {weight} exceeds 1.0"

    # All weights should be positive
    for dim, weight in result.items():
        assert weight > 0, f"{dim} weight {weight} is not positive"


def test_adapt_weights_large_feedback_dataset_performance() -> None:
    """Verify reasonable performance with large feedback dataset (1000+ rows)."""
    import time

    # Generate 1000 feedback outcomes
    outcomes = []
    random.seed(42)
    for i in range(1000):
        outcomes.append({
            "dimension_values": {dim: random.uniform(0, 10) for dim in DEFAULT_WEIGHTS},
            "success": i % 2 == 0,  # Alternate success/failure
        })

    # Time the adaptation
    start = time.time()
    result = adapt_weights(outcomes)
    elapsed = time.time() - start

    # Should complete in reasonable time (< 1 second for 1000 rows)
    assert elapsed < 1.0, f"adapt_weights took {elapsed:.2f}s for 1000 rows"

    # Result should still be valid
    assert len(result) == 7
    assert abs(sum(result.values()) - 1.0) < 0.001
    assert all(w > 0 for w in result.values())
    assert all(w <= 1.0 for w in result.values())


# ============================================================================
# 4. get_adapted_weights
# ============================================================================


def test_get_adapted_weights_empty_feedback() -> None:
    """Empty feedback should return (base_weights, False)."""
    weights, was_adapted = get_adapted_weights("default", [])
    assert weights == DEFAULT_WEIGHTS
    assert was_adapted is False


def test_get_adapted_weights_feedback_without_dimension_values() -> None:
    """Feedback without dimension_values should return (base_weights, False)."""
    feedback = [
        {"success": True},  # Missing dimension_values
        {"success": False},
    ]
    weights, was_adapted = get_adapted_weights("default", feedback)
    assert weights == DEFAULT_WEIGHTS
    assert was_adapted is False


def test_get_adapted_weights_only_successes() -> None:
    """Only successes should return (base_weights, False)."""
    feedback = [
        {
            "dimension_values": {dim: 8.0 for dim in DEFAULT_WEIGHTS},
            "success": True,
        },
        {
            "dimension_values": {dim: 7.0 for dim in DEFAULT_WEIGHTS},
            "success": True,
        },
    ]
    weights, was_adapted = get_adapted_weights("default", feedback)
    assert weights == DEFAULT_WEIGHTS
    assert was_adapted is False


def test_get_adapted_weights_only_failures() -> None:
    """Only failures should return (base_weights, False)."""
    feedback = [
        {
            "dimension_values": {dim: 3.0 for dim in DEFAULT_WEIGHTS},
            "success": False,
        },
        {
            "dimension_values": {dim: 2.0 for dim in DEFAULT_WEIGHTS},
            "success": False,
        },
    ]
    weights, was_adapted = get_adapted_weights("default", feedback)
    assert weights == DEFAULT_WEIGHTS
    assert was_adapted is False


def test_get_adapted_weights_mixed_valid_feedback() -> None:
    """Mixed valid feedback should return (adapted_weights, True)."""
    feedback = [
        {
            "dimension_values": {dim: 8.0 for dim in DEFAULT_WEIGHTS},
            "success": True,
        },
        {
            "dimension_values": {dim: 3.0 for dim in DEFAULT_WEIGHTS},
            "success": False,
        },
    ]
    weights, was_adapted = get_adapted_weights("default", feedback)
    assert was_adapted is True
    # Weights should be different from base (adapted)
    assert weights != DEFAULT_WEIGHTS
    # Should still sum to 1.0
    assert abs(sum(weights.values()) - 1.0) < 0.001


def test_get_adapted_weights_uses_profile() -> None:
    """get_adapted_weights should use the specified profile as base."""
    feedback = [
        {
            "dimension_values": {dim: 8.0 for dim in DEFAULT_WEIGHTS},
            "success": True,
        },
        {
            "dimension_values": {dim: 3.0 for dim in DEFAULT_WEIGHTS},
            "success": False,
        },
    ]
    weights_default, _ = get_adapted_weights("default", feedback)
    weights_quick, _ = get_adapted_weights("quick_wins", feedback)

    # Different profiles should produce different adapted weights
    # (since they start from different bases)
    assert weights_default != weights_quick


def test_get_adapted_weights_learning_rate() -> None:
    """get_adapted_weights should respect learning_rate parameter."""
    feedback = [
        {
            "dimension_values": {
                "pain_severity": 9.0,
                "addressable_scale": 5.0,
                "build_effort": 5.0,
                "composability": 5.0,
                "competitive_density": 5.0,
                "timing_fit": 5.0,
                "compounding_value": 5.0,
            },
            "success": True,
        },
        {
            "dimension_values": {
                "pain_severity": 2.0,
                "addressable_scale": 5.0,
                "build_effort": 5.0,
                "composability": 5.0,
                "competitive_density": 5.0,
                "timing_fit": 5.0,
                "compounding_value": 5.0,
            },
            "success": False,
        },
    ]

    weights_low, _ = get_adapted_weights("default", feedback, learning_rate=0.01)
    weights_high, _ = get_adapted_weights("default", feedback, learning_rate=0.10)

    # Different learning rates should produce different results
    assert weights_low != weights_high


def test_get_adapted_weights_filters_invalid_outcomes() -> None:
    """get_adapted_weights should filter out outcomes without dimension_values."""
    feedback = [
        {
            "dimension_values": {dim: 8.0 for dim in DEFAULT_WEIGHTS},
            "success": True,
        },
        {"success": False},  # Missing dimension_values
        {
            "dimension_values": {dim: 3.0 for dim in DEFAULT_WEIGHTS},
            "success": False,
        },
    ]
    weights, was_adapted = get_adapted_weights("default", feedback)
    # Should still adapt based on the 2 valid outcomes
    assert was_adapted is True


def test_get_adapted_weights_all_filtered_out() -> None:
    """If all outcomes are filtered out, should return (base_weights, False)."""
    feedback = [
        {"success": True},  # No dimension_values
        {"success": False},  # No dimension_values
    ]
    weights, was_adapted = get_adapted_weights("default", feedback)
    assert weights == DEFAULT_WEIGHTS
    assert was_adapted is False


# ============================================================================
# 5. save_weights / load_weights
# ============================================================================


def test_save_and_load_weights_roundtrip(tmp_path: Path) -> None:
    """Save then load should return the same weights."""
    weights = {
        "pain_severity": 0.25,
        "addressable_scale": 0.20,
        "build_effort": 0.15,
        "composability": 0.15,
        "competitive_density": 0.10,
        "timing_fit": 0.05,
        "compounding_value": 0.10,
    }

    path = tmp_path / "test_weights.json"
    save_weights(weights, path)
    loaded = load_weights(path)

    assert loaded == weights


def test_save_weights_json_format(tmp_path: Path) -> None:
    """save_weights should use JSON format."""
    weights = DEFAULT_WEIGHTS.copy()
    path = tmp_path / "weights.json"

    save_weights(weights, path)

    # Verify it's valid JSON
    with open(path) as f:
        data = json.load(f)

    assert data == weights


def test_save_weights_indented(tmp_path: Path) -> None:
    """save_weights should use indented JSON for readability."""
    weights = DEFAULT_WEIGHTS.copy()
    path = tmp_path / "weights.json"

    save_weights(weights, path)

    # Read the raw content
    content = path.read_text()

    # Should have newlines (indented)
    assert "\n" in content
    # Should have indentation
    assert "  " in content


def test_load_weights_from_file(tmp_path: Path) -> None:
    """load_weights should correctly parse JSON file."""
    weights = {
        "dim_a": 0.6,
        "dim_b": 0.4,
    }
    path = tmp_path / "custom.json"

    # Write JSON manually
    with open(path, "w") as f:
        json.dump(weights, f)

    loaded = load_weights(path)
    assert loaded == weights


def test_save_weights_preserves_precision(tmp_path: Path) -> None:
    """save_weights should preserve float precision."""
    weights = {
        "pain_severity": 0.123456,
        "addressable_scale": 0.876544,
    }
    path = tmp_path / "precise.json"

    save_weights(weights, path)
    loaded = load_weights(path)

    # Should preserve precision
    assert loaded["pain_severity"] == pytest.approx(0.123456)
    assert loaded["addressable_scale"] == pytest.approx(0.876544)
