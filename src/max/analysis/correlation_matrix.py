"""Signal correlation matrix analysis module.

Calculates pairwise Pearson and Spearman correlation coefficients across
signal metrics. Highlights strong positive/negative correlations to surface
unexpected connections between ecosystem data points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class CorrelationMethod(StrEnum):
    PEARSON = "pearson"
    SPEARMAN = "spearman"


@dataclass(frozen=True)
class CorrelationEntry:
    """Single pairwise correlation result."""

    metric_a: str
    metric_b: str
    coefficient: float
    p_value: float
    significant: bool


class CorrelationMatrix:
    """Calculates pairwise Pearson and Spearman correlation coefficients.

    Identifies statistically significant correlations above a threshold.
    Outputs matrix as dict-of-dicts with p-values and significance flags.
    """

    def __init__(self, *, significance_threshold: float = 0.5) -> None:
        """Initialize correlation matrix analyzer.

        Args:
            significance_threshold: Absolute correlation coefficient above
                which a correlation is flagged as significant.
        """
        self._threshold = significance_threshold

    def compute(
        self,
        data: dict[str, list[float]],
        *,
        method: CorrelationMethod | str = CorrelationMethod.PEARSON,
    ) -> dict[str, dict[str, CorrelationEntry]]:
        """Compute pairwise correlation matrix.

        Args:
            data: Dict mapping metric names to lists of float values.
                All lists must be the same length.
            method: Correlation method to use.

        Returns:
            Nested dict: matrix[metric_a][metric_b] = CorrelationEntry
        """
        metrics = sorted(data.keys())
        if not metrics:
            return {}

        # Validate lengths
        lengths = {len(v) for v in data.values()}
        if len(lengths) > 1:
            raise ValueError("All metric series must have the same length")
        n = lengths.pop()
        if n < 3:
            raise ValueError("Need at least 3 data points for correlation")

        method_str = str(method)
        matrix: dict[str, dict[str, CorrelationEntry]] = {}

        for a in metrics:
            matrix[a] = {}
            for b in metrics:
                if a == b:
                    matrix[a][b] = CorrelationEntry(
                        metric_a=a, metric_b=b,
                        coefficient=1.0, p_value=0.0, significant=True,
                    )
                elif b in matrix and a in matrix[b]:
                    # Symmetric: reuse computed value
                    existing = matrix[b][a]
                    matrix[a][b] = CorrelationEntry(
                        metric_a=a, metric_b=b,
                        coefficient=existing.coefficient,
                        p_value=existing.p_value,
                        significant=existing.significant,
                    )
                else:
                    x = data[a]
                    y = data[b]
                    if method_str == CorrelationMethod.SPEARMAN:
                        x = _rank(x)
                        y = _rank(y)
                    coeff = _pearson(x, y)
                    p_val = _p_value_approx(coeff, n)
                    matrix[a][b] = CorrelationEntry(
                        metric_a=a, metric_b=b,
                        coefficient=round(coeff, 4),
                        p_value=round(p_val, 4),
                        significant=abs(coeff) >= self._threshold,
                    )

        return matrix

    def significant_pairs(
        self,
        data: dict[str, list[float]],
        *,
        method: CorrelationMethod | str = CorrelationMethod.PEARSON,
    ) -> list[CorrelationEntry]:
        """Return only significant correlations (excluding self-correlations).

        Sorted by absolute coefficient descending.
        """
        matrix = self.compute(data, method=method)
        seen: set[tuple[str, str]] = set()
        results: list[CorrelationEntry] = []

        for a, row in matrix.items():
            for b, entry in row.items():
                if a == b:
                    continue
                pair = (min(a, b), max(a, b))
                if pair in seen:
                    continue
                seen.add(pair)
                if entry.significant:
                    results.append(entry)

        results.sort(key=lambda e: abs(e.coefficient), reverse=True)
        return results

    def to_dict(
        self,
        data: dict[str, list[float]],
        *,
        method: CorrelationMethod | str = CorrelationMethod.PEARSON,
    ) -> dict[str, dict[str, dict]]:
        """Compute and return matrix as plain dict-of-dicts with p-values."""
        matrix = self.compute(data, method=method)
        result: dict[str, dict[str, dict]] = {}
        for a, row in matrix.items():
            result[a] = {}
            for b, entry in row.items():
                result[a][b] = {
                    "coefficient": entry.coefficient,
                    "p_value": entry.p_value,
                    "significant": entry.significant,
                }
        return result


# ── Statistical helpers ──────────────────────────────────────────────


def _pearson(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient between two series."""
    n = len(x)
    if n == 0:
        return 0.0

    x_mean = sum(x) / n
    y_mean = sum(y) / n

    numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    denom_x = math.sqrt(sum((xi - x_mean) ** 2 for xi in x))
    denom_y = math.sqrt(sum((yi - y_mean) ** 2 for yi in y))

    if denom_x == 0 or denom_y == 0:
        return 0.0

    return numerator / (denom_x * denom_y)


def _rank(values: list[float]) -> list[float]:
    """Compute ranks for Spearman correlation (average rank for ties)."""
    indexed = sorted(enumerate(values), key=lambda t: t[1])
    ranks = [0.0] * len(values)

    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) - 1 and indexed[j + 1][1] == indexed[j][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-based
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1

    return ranks


def _p_value_approx(r: float, n: int) -> float:
    """Approximate p-value for correlation coefficient using t-distribution.

    Uses a rough approximation suitable for screening significance.
    """
    if abs(r) >= 1.0 or n < 3:
        return 0.0

    t_stat = r * math.sqrt((n - 2) / (1 - r ** 2))
    # Approximate two-tailed p-value using normal approximation
    # (adequate for n > ~20, rough for smaller n)
    df = n - 2
    abs_t = abs(t_stat)

    # Use simple approximation: p ≈ 2 * (1 - Φ(|t|)) for large df
    # For smaller df, this overestimates p slightly (conservative)
    z = abs_t / math.sqrt(1 + abs_t ** 2 / df) if df > 0 else abs_t
    p = 2.0 * (1.0 - _normal_cdf(z))
    return max(0.0, min(1.0, p))


def _normal_cdf(x: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
