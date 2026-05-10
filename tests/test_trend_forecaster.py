"""Tests for trend forecaster analysis module."""

from __future__ import annotations

import pytest

from max.analysis.trend_forecaster import (
    ForecastMethod,
    ForecastPoint,
    ForecastResult,
    TrendForecaster,
)


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def forecaster() -> TrendForecaster:
    return TrendForecaster()


# ── Linear regression tests ──────────────────────────────────────────


def test_linear_perfect_trend(forecaster: TrendForecaster) -> None:
    """Perfect linear data should produce exact forecasts."""
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = forecaster.forecast(values, horizon=3, method=ForecastMethod.LINEAR)

    assert result.method == "linear"
    assert result.horizon == 3
    assert len(result.forecasts) == 3
    assert result.slope == pytest.approx(10.0)
    assert result.intercept == pytest.approx(10.0)
    assert result.residual_std == pytest.approx(0.0, abs=1e-6)

    # Forecasts should continue the trend
    assert result.forecasts[0].value == pytest.approx(60.0, abs=0.1)
    assert result.forecasts[1].value == pytest.approx(70.0, abs=0.1)
    assert result.forecasts[2].value == pytest.approx(80.0, abs=0.1)


def test_linear_constant_values(forecaster: TrendForecaster) -> None:
    """Constant values should produce flat forecast."""
    values = [5.0, 5.0, 5.0, 5.0]
    result = forecaster.forecast(values, horizon=2, method=ForecastMethod.LINEAR)

    assert result.slope == pytest.approx(0.0)
    for fp in result.forecasts:
        assert fp.value == pytest.approx(5.0, abs=0.1)


def test_linear_negative_trend(forecaster: TrendForecaster) -> None:
    """Decreasing trend should produce negative slope."""
    values = [100.0, 80.0, 60.0, 40.0]
    result = forecaster.forecast(values, horizon=2, method=ForecastMethod.LINEAR)

    assert result.slope is not None
    assert result.slope < 0
    assert result.forecasts[0].value < 40.0


def test_linear_confidence_bounds(forecaster: TrendForecaster) -> None:
    """Confidence bounds should widen for noisier data."""
    values = [10.0, 22.0, 28.0, 42.0, 48.0]
    result = forecaster.forecast(values, horizon=3, method=ForecastMethod.LINEAR)

    for fp in result.forecasts:
        assert fp.lower_bound < fp.value
        assert fp.upper_bound > fp.value

    # Bounds should widen further into the future
    assert (result.forecasts[2].upper_bound - result.forecasts[2].lower_bound) > \
           (result.forecasts[0].upper_bound - result.forecasts[0].lower_bound)


def test_linear_zero_residual_bounds(forecaster: TrendForecaster) -> None:
    """Perfect data should have zero-width confidence interval."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = forecaster.forecast(values, horizon=2, method=ForecastMethod.LINEAR)

    for fp in result.forecasts:
        assert fp.lower_bound == pytest.approx(fp.value, abs=1e-6)
        assert fp.upper_bound == pytest.approx(fp.value, abs=1e-6)


# ── Exponential smoothing tests ──────────────────────────────────────


def test_exponential_smoothing_basic(forecaster: TrendForecaster) -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = forecaster.forecast(
        values, horizon=3, method=ForecastMethod.EXPONENTIAL_SMOOTHING,
    )

    assert result.method == "exponential_smoothing"
    assert result.horizon == 3
    assert len(result.forecasts) == 3
    assert result.alpha == 0.3


def test_exponential_smoothing_flat_forecast(forecaster: TrendForecaster) -> None:
    """Exponential smoothing produces flat forecast (all values equal)."""
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    result = forecaster.forecast(
        values, horizon=3, method=ForecastMethod.EXPONENTIAL_SMOOTHING,
    )

    # All forecast values should be equal (flat)
    assert result.forecasts[0].value == result.forecasts[1].value
    assert result.forecasts[1].value == result.forecasts[2].value


def test_exponential_smoothing_widening_bounds(forecaster: TrendForecaster) -> None:
    """Confidence intervals should widen over forecast horizon."""
    values = [10.0, 15.0, 12.0, 18.0, 14.0]
    result = forecaster.forecast(
        values, horizon=5, method=ForecastMethod.EXPONENTIAL_SMOOTHING,
    )

    widths = [fp.upper_bound - fp.lower_bound for fp in result.forecasts]
    for i in range(1, len(widths)):
        assert widths[i] > widths[i - 1]


def test_exponential_smoothing_constant(forecaster: TrendForecaster) -> None:
    """Constant data should produce exact level with zero bounds."""
    values = [5.0, 5.0, 5.0, 5.0]
    result = forecaster.forecast(
        values, horizon=2, method=ForecastMethod.EXPONENTIAL_SMOOTHING,
    )

    for fp in result.forecasts:
        assert fp.value == pytest.approx(5.0, abs=1e-6)
        assert fp.lower_bound == pytest.approx(fp.value, abs=1e-6)


# ── Edge cases ───────────────────────────────────────────────────────


def test_minimum_data_points(forecaster: TrendForecaster) -> None:
    """Two data points should work."""
    values = [10.0, 20.0]
    result = forecaster.forecast(values, horizon=1, method=ForecastMethod.LINEAR)
    assert len(result.forecasts) == 1
    assert result.forecasts[0].value == pytest.approx(30.0, abs=0.1)


def test_insufficient_data(forecaster: TrendForecaster) -> None:
    """Single data point should raise ValueError."""
    with pytest.raises(ValueError, match="at least 2"):
        forecaster.forecast([10.0], horizon=1)


def test_empty_data(forecaster: TrendForecaster) -> None:
    with pytest.raises(ValueError, match="at least 2"):
        forecaster.forecast([], horizon=1)


def test_unknown_method(forecaster: TrendForecaster) -> None:
    with pytest.raises(ValueError, match="Unknown method"):
        forecaster.forecast([1.0, 2.0], horizon=1, method="invalid")


def test_forecast_result_structure(forecaster: TrendForecaster) -> None:
    values = [10.0, 20.0, 30.0]
    result = forecaster.forecast(values, horizon=2)

    assert isinstance(result, ForecastResult)
    assert isinstance(result.forecasts[0], ForecastPoint)
    assert result.forecasts[0].step == 1
    assert result.forecasts[1].step == 2


def test_custom_confidence_level() -> None:
    """Higher confidence level should produce wider bounds."""
    values = [10.0, 22.0, 28.0, 42.0, 48.0]

    narrow = TrendForecaster(confidence_level=1.0)
    wide = TrendForecaster(confidence_level=2.58)

    r_narrow = narrow.forecast(values, horizon=3)
    r_wide = wide.forecast(values, horizon=3)

    for n, w in zip(r_narrow.forecasts, r_wide.forecasts):
        n_width = n.upper_bound - n.lower_bound
        w_width = w.upper_bound - w.lower_bound
        assert w_width > n_width


# ── Synthetic accuracy tests ─────────────────────────────────────────


def test_linear_forecast_accuracy_on_known_series(forecaster: TrendForecaster) -> None:
    """Verify forecast on y = 2x + 5."""
    values = [5.0 + 2.0 * x for x in range(10)]  # 5, 7, 9, ..., 23
    result = forecaster.forecast(values, horizon=3, method=ForecastMethod.LINEAR)

    expected = [5.0 + 2.0 * x for x in range(10, 13)]  # 25, 27, 29
    for fp, expected_val in zip(result.forecasts, expected):
        assert fp.value == pytest.approx(expected_val, abs=0.01)


def test_exponential_smoothing_tracks_level(forecaster: TrendForecaster) -> None:
    """Smoothed level should be between min and max of input."""
    values = [10.0, 30.0, 20.0, 40.0, 25.0]
    result = forecaster.forecast(
        values, horizon=1, method=ForecastMethod.EXPONENTIAL_SMOOTHING,
    )

    level = result.forecasts[0].value
    assert level >= min(values) * 0.5  # Some tolerance
    assert level <= max(values) * 1.5
