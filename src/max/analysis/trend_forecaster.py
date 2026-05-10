"""Trend forecaster analysis module.

Projects future signal trends from historical time-series data using
simple linear regression and exponential smoothing. Outputs forecast
values with confidence intervals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class ForecastMethod(StrEnum):
    LINEAR = "linear"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"


@dataclass(frozen=True)
class ForecastPoint:
    """Single forecast data point with confidence bounds."""

    step: int
    value: float
    lower_bound: float
    upper_bound: float


@dataclass(frozen=True)
class ForecastResult:
    """Complete forecast result."""

    method: str
    horizon: int
    forecasts: list[ForecastPoint]
    slope: float | None = None  # linear regression slope
    intercept: float | None = None  # linear regression intercept
    alpha: float | None = None  # smoothing factor
    residual_std: float | None = None


class TrendForecaster:
    """Forecasts future values from historical time-series data.

    Supports linear regression and exponential smoothing methods.
    Returns forecast values with upper/lower confidence bounds.
    """

    def __init__(self, *, confidence_level: float = 1.96) -> None:
        """Initialize forecaster.

        Args:
            confidence_level: z-score multiplier for confidence interval.
                Default 1.96 for ~95% confidence.
        """
        self._z = confidence_level

    def forecast(
        self,
        values: list[float],
        *,
        horizon: int = 5,
        method: ForecastMethod | str = ForecastMethod.LINEAR,
    ) -> ForecastResult:
        """Produce a forecast from historical time-series values.

        Args:
            values: Historical observations (ordered by time).
            horizon: Number of future steps to forecast.
            method: Forecasting method to use.

        Returns:
            ForecastResult with forecast points and model parameters.
        """
        if len(values) < 2:
            raise ValueError("Need at least 2 data points for forecasting")

        method_str = str(method)
        if method_str == ForecastMethod.LINEAR:
            return self._linear_regression(values, horizon)
        elif method_str == ForecastMethod.EXPONENTIAL_SMOOTHING:
            return self._exponential_smoothing(values, horizon)
        else:
            raise ValueError(f"Unknown method: {method}")

    def _linear_regression(
        self, values: list[float], horizon: int,
    ) -> ForecastResult:
        """Simple linear regression forecast."""
        n = len(values)
        x_vals = list(range(n))

        # Calculate means
        x_mean = sum(x_vals) / n
        y_mean = sum(values) / n

        # Calculate slope and intercept
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, values))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)

        if denominator == 0:
            slope = 0.0
        else:
            slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # Calculate residual standard deviation
        predictions = [slope * x + intercept for x in x_vals]
        residuals = [actual - pred for actual, pred in zip(values, predictions)]
        if n > 2:
            residual_std = math.sqrt(sum(r ** 2 for r in residuals) / (n - 2))
        else:
            residual_std = 0.0

        # Generate forecasts
        forecasts: list[ForecastPoint] = []
        for step in range(1, horizon + 1):
            x = n - 1 + step
            value = slope * x + intercept
            margin = self._z * residual_std * math.sqrt(1 + 1 / n + (x - x_mean) ** 2 / denominator) if denominator > 0 else 0.0
            forecasts.append(ForecastPoint(
                step=step,
                value=round(value, 4),
                lower_bound=round(value - margin, 4),
                upper_bound=round(value + margin, 4),
            ))

        return ForecastResult(
            method=ForecastMethod.LINEAR,
            horizon=horizon,
            forecasts=forecasts,
            slope=round(slope, 4),
            intercept=round(intercept, 4),
            residual_std=round(residual_std, 4),
        )

    def _exponential_smoothing(
        self, values: list[float], horizon: int, alpha: float = 0.3,
    ) -> ForecastResult:
        """Simple exponential smoothing forecast."""
        n = len(values)

        # Apply exponential smoothing to get fitted values
        smoothed = [values[0]]
        for i in range(1, n):
            s = alpha * values[i] + (1 - alpha) * smoothed[-1]
            smoothed.append(s)

        # Last smoothed value is the level for forecasting
        level = smoothed[-1]

        # Calculate residual std from in-sample errors
        residuals = [values[i] - smoothed[i] for i in range(n)]
        if n > 1:
            residual_std = math.sqrt(sum(r ** 2 for r in residuals) / (n - 1))
        else:
            residual_std = 0.0

        # Forecast: flat line at level with widening confidence interval
        forecasts: list[ForecastPoint] = []
        for step in range(1, horizon + 1):
            margin = self._z * residual_std * math.sqrt(step)
            forecasts.append(ForecastPoint(
                step=step,
                value=round(level, 4),
                lower_bound=round(level - margin, 4),
                upper_bound=round(level + margin, 4),
            ))

        return ForecastResult(
            method=ForecastMethod.EXPONENTIAL_SMOOTHING,
            horizon=horizon,
            forecasts=forecasts,
            alpha=alpha,
            residual_std=round(residual_std, 4),
        )
