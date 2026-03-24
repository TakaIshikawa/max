"""Tests for evaluation weight computation."""

from __future__ import annotations

from max.evaluation.weights import DEFAULT_WEIGHTS, compute_overall_score


def test_default_weights_sum_to_one() -> None:
    total = sum(DEFAULT_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001


def test_compute_overall_score_perfect() -> None:
    values = {dim: 10.0 for dim in DEFAULT_WEIGHTS}
    score = compute_overall_score(values)
    assert score == 100.0


def test_compute_overall_score_zero() -> None:
    values = {dim: 0.0 for dim in DEFAULT_WEIGHTS}
    score = compute_overall_score(values)
    assert score == 0.0


def test_compute_overall_score_mid() -> None:
    values = {dim: 5.0 for dim in DEFAULT_WEIGHTS}
    score = compute_overall_score(values)
    assert score == 50.0


def test_compute_overall_score_weighted() -> None:
    # Only pain_severity at max, rest at 0
    values = {dim: 0.0 for dim in DEFAULT_WEIGHTS}
    values["pain_severity"] = 10.0
    score = compute_overall_score(values)
    # 10 * 0.20 * 10 = 20.0
    assert score == 20.0


def test_custom_weights() -> None:
    values = {"pain_severity": 10.0}
    custom = {"pain_severity": 1.0}
    score = compute_overall_score(values, weights=custom)
    assert score == 100.0
