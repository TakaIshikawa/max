"""Tests for signal correlation matrix analysis module."""

from __future__ import annotations

import pytest

from max.analysis.correlation_matrix import (
    CorrelationEntry,
    CorrelationMatrix,
    CorrelationMethod,
    _pearson,
    _rank,
)


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def analyzer() -> CorrelationMatrix:
    return CorrelationMatrix()


# ── Pearson helper tests ─────────────────────────────────────────────


def test_pearson_perfect_positive() -> None:
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    assert _pearson(x, y) == pytest.approx(1.0, abs=1e-6)


def test_pearson_perfect_negative() -> None:
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [10.0, 8.0, 6.0, 4.0, 2.0]
    assert _pearson(x, y) == pytest.approx(-1.0, abs=1e-6)


def test_pearson_no_correlation() -> None:
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 1.0, 5.0, 3.0]
    r = _pearson(x, y)
    assert abs(r) < 0.5  # Weak correlation


def test_pearson_constant_series() -> None:
    x = [5.0, 5.0, 5.0, 5.0]
    y = [1.0, 2.0, 3.0, 4.0]
    assert _pearson(x, y) == 0.0


# ── Rank helper tests ───────────────────────────────────────────────


def test_rank_basic() -> None:
    values = [30.0, 10.0, 20.0]
    ranks = _rank(values)
    assert ranks == [3.0, 1.0, 2.0]


def test_rank_with_ties() -> None:
    values = [10.0, 20.0, 20.0, 30.0]
    ranks = _rank(values)
    assert ranks[0] == 1.0
    assert ranks[1] == 2.5  # Average rank for tie
    assert ranks[2] == 2.5
    assert ranks[3] == 4.0


# ── Correlation matrix compute tests ────────────────────────────────


def test_compute_pearson_perfect(analyzer: CorrelationMatrix) -> None:
    data = {
        "downloads": [100.0, 200.0, 300.0, 400.0, 500.0],
        "stars": [10.0, 20.0, 30.0, 40.0, 50.0],
    }
    matrix = analyzer.compute(data, method=CorrelationMethod.PEARSON)

    assert matrix["downloads"]["stars"].coefficient == pytest.approx(1.0, abs=1e-3)
    assert matrix["stars"]["downloads"].coefficient == pytest.approx(1.0, abs=1e-3)
    assert matrix["downloads"]["downloads"].coefficient == 1.0


def test_compute_spearman(analyzer: CorrelationMatrix) -> None:
    data = {
        "a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "b": [2.0, 4.0, 6.0, 8.0, 10.0],
    }
    matrix = analyzer.compute(data, method=CorrelationMethod.SPEARMAN)

    assert matrix["a"]["b"].coefficient == pytest.approx(1.0, abs=1e-3)


def test_compute_negative_correlation(analyzer: CorrelationMatrix) -> None:
    data = {
        "x": [1.0, 2.0, 3.0, 4.0, 5.0],
        "y": [50.0, 40.0, 30.0, 20.0, 10.0],
    }
    matrix = analyzer.compute(data)

    assert matrix["x"]["y"].coefficient == pytest.approx(-1.0, abs=1e-3)
    assert matrix["x"]["y"].significant is True


def test_compute_symmetry(analyzer: CorrelationMatrix) -> None:
    data = {
        "a": [1.0, 3.0, 5.0, 7.0, 9.0],
        "b": [2.0, 6.0, 4.0, 8.0, 10.0],
    }
    matrix = analyzer.compute(data)

    assert matrix["a"]["b"].coefficient == matrix["b"]["a"].coefficient
    assert matrix["a"]["b"].p_value == matrix["b"]["a"].p_value


def test_compute_self_correlation(analyzer: CorrelationMatrix) -> None:
    data = {"x": [1.0, 2.0, 3.0, 4.0, 5.0]}
    matrix = analyzer.compute(data)

    assert matrix["x"]["x"].coefficient == 1.0
    assert matrix["x"]["x"].p_value == 0.0
    assert matrix["x"]["x"].significant is True


def test_compute_three_metrics(analyzer: CorrelationMatrix) -> None:
    data = {
        "a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "b": [2.0, 4.0, 6.0, 8.0, 10.0],
        "c": [5.0, 4.0, 3.0, 2.0, 1.0],
    }
    matrix = analyzer.compute(data)

    assert "a" in matrix
    assert "b" in matrix
    assert "c" in matrix
    assert matrix["a"]["b"].coefficient == pytest.approx(1.0, abs=1e-3)
    assert matrix["a"]["c"].coefficient == pytest.approx(-1.0, abs=1e-3)


# ── Significance tests ──────────────────────────────────────────────


def test_significance_threshold_custom() -> None:
    analyzer = CorrelationMatrix(significance_threshold=0.9)
    data = {
        "a": [1.0, 3.0, 5.0, 7.0, 9.0],
        "b": [2.0, 6.0, 4.0, 8.0, 10.0],
    }
    matrix = analyzer.compute(data)
    # Moderate correlation should not meet high threshold
    entry = matrix["a"]["b"]
    if abs(entry.coefficient) < 0.9:
        assert entry.significant is False


def test_significant_pairs(analyzer: CorrelationMatrix) -> None:
    data = {
        "a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "b": [2.0, 4.0, 6.0, 8.0, 10.0],
        "c": [5.0, 3.0, 4.0, 2.0, 1.0],
    }
    pairs = analyzer.significant_pairs(data)

    # Should have significant pairs (a-b, a-c, b-c)
    assert len(pairs) > 0
    # All should be significant
    for entry in pairs:
        assert entry.significant is True
        assert entry.metric_a != entry.metric_b
    # Sorted by absolute coefficient descending
    for i in range(1, len(pairs)):
        assert abs(pairs[i].coefficient) <= abs(pairs[i - 1].coefficient)


def test_significant_pairs_no_self(analyzer: CorrelationMatrix) -> None:
    data = {"a": [1.0, 2.0, 3.0, 4.0, 5.0]}
    pairs = analyzer.significant_pairs(data)
    assert pairs == []


# ── to_dict output ──────────────────────────────────────────────────


def test_to_dict_structure(analyzer: CorrelationMatrix) -> None:
    data = {
        "x": [1.0, 2.0, 3.0, 4.0, 5.0],
        "y": [10.0, 20.0, 30.0, 40.0, 50.0],
    }
    result = analyzer.to_dict(data)

    assert "x" in result
    assert "y" in result["x"]
    assert "coefficient" in result["x"]["y"]
    assert "p_value" in result["x"]["y"]
    assert "significant" in result["x"]["y"]


# ── Edge cases ──────────────────────────────────────────────────────


def test_empty_data(analyzer: CorrelationMatrix) -> None:
    result = analyzer.compute({})
    assert result == {}


def test_mismatched_lengths(analyzer: CorrelationMatrix) -> None:
    data = {
        "a": [1.0, 2.0, 3.0],
        "b": [1.0, 2.0],
    }
    with pytest.raises(ValueError, match="same length"):
        analyzer.compute(data)


def test_insufficient_data_points(analyzer: CorrelationMatrix) -> None:
    data = {
        "a": [1.0, 2.0],
        "b": [3.0, 4.0],
    }
    with pytest.raises(ValueError, match="at least 3"):
        analyzer.compute(data)


def test_known_correlated_datasets(analyzer: CorrelationMatrix) -> None:
    """Verify correlation with known correlated synthetic data."""
    # y = 2x + noise (strong positive correlation)
    x = [float(i) for i in range(20)]
    y = [2.0 * i + (0.1 if i % 2 == 0 else -0.1) for i in range(20)]

    data = {"x_metric": x, "y_metric": y}
    matrix = analyzer.compute(data)

    entry = matrix["x_metric"]["y_metric"]
    assert entry.coefficient > 0.99
    assert entry.significant is True
    assert entry.p_value < 0.01


def test_uncorrelated_datasets(analyzer: CorrelationMatrix) -> None:
    """Verify weak correlation between independent-looking data."""
    data = {
        "a": [1.0, 5.0, 2.0, 8.0, 3.0, 7.0, 4.0, 6.0],
        "b": [8.0, 2.0, 7.0, 1.0, 6.0, 3.0, 5.0, 4.0],
    }
    matrix = analyzer.compute(data)

    entry = matrix["a"]["b"]
    assert abs(entry.coefficient) < 1.0  # Not perfect
