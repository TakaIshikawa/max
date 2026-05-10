"""Tests for quarterly business review export."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.quarterly_review import (
    SCHEMA_VERSION,
    KIND,
    STATUS_GREEN,
    STATUS_RED,
    TREND_UP,
    TREND_FLAT,
    build_quarterly_review,
    render_quarterly_review_json,
    render_quarterly_review_markdown,
    _compile_metrics,
    _assess_goal_progress,
    _extract_achievements,
    _extract_priorities,
    _build_quarter_comparisons,
)
from max.types.signal import Signal, SignalSourceType


# ── Helpers ──────────────────────────────────────────────────────────


def _make_unit(
    *,
    unit_id: str = "bu-001",
    solution: str = "Platform feature",
    domain: str = "devtools",
    quality_score: float = 0.8,
    value_proposition: str = "Faster dev cycles",
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.solution = solution
    unit.domain = domain
    unit.quality_score = quality_score
    unit.value_proposition = value_proposition
    return unit


def _make_signal(
    *,
    signal_id: str = "sig-001",
    title: str = "Signal",
    content: str = "Content",
    tags: list[str] | None = None,
    source_type: SignalSourceType = SignalSourceType.MARKET,
) -> Signal:
    return Signal(
        id=signal_id,
        title=title,
        content=content,
        source_type=source_type,
        source_adapter="test_adapter",
        url="https://example.com",
        tags=tags or [],
    )


def _mock_store(
    units: list | None = None,
    signals: list | None = None,
) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    store.get_signals.return_value = signals or []
    return store


# ── Schema and structure tests ───────────────────────────────────────


def test_build_quarterly_review_schema() -> None:
    store = _mock_store()
    result = build_quarterly_review(store)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert "generated_at" in result
    assert "quarter" in result
    assert "metrics" in result
    assert "goal_progress" in result
    assert "key_achievements" in result
    assert "next_quarter_priorities" in result
    assert "quarter_comparisons" in result


def test_build_quarterly_review_domain_filter() -> None:
    store = _mock_store()
    build_quarterly_review(store, domain="security")
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="security")


def test_build_quarterly_review_custom_quarter() -> None:
    store = _mock_store()
    result = build_quarterly_review(store, quarter="Q3 2025")
    assert result["quarter"] == "Q3 2025"


def test_build_quarterly_review_auto_quarter() -> None:
    store = _mock_store()
    result = build_quarterly_review(store)
    assert result["quarter"].startswith("Q")


# ── Metrics tests ────────────────────────────────────────────────────


def test_compile_metrics_basic() -> None:
    units = [_make_unit()]
    signals = [_make_signal()]
    metrics = _compile_metrics(units, signals)
    names = {m["name"] for m in metrics}
    assert "Signals Collected" in names
    assert "Buildable Units" in names
    assert "Avg Quality Score" in names


def test_compile_metrics_empty() -> None:
    metrics = _compile_metrics([], [])
    assert len(metrics) == 2  # Signal count + unit count
    assert metrics[0]["trend"] == TREND_FLAT


def test_compile_metrics_trends() -> None:
    units = [_make_unit(quality_score=0.9)]
    signals = [_make_signal()]
    metrics = _compile_metrics(units, signals)
    signal_metric = next(m for m in metrics if m["name"] == "Signals Collected")
    assert signal_metric["trend"] == TREND_UP


# ── Goal progress tests ─────────────────────────────────────────────


def test_assess_goal_progress_high_quality() -> None:
    units = [_make_unit(quality_score=0.9)]
    goals = _assess_goal_progress(units)
    quality_goal = next(g for g in goals if g["goal"] == "Unit Quality")
    assert quality_goal["status"] == STATUS_GREEN


def test_assess_goal_progress_low_quality() -> None:
    units = [_make_unit(quality_score=0.2)]
    goals = _assess_goal_progress(units)
    quality_goal = next(g for g in goals if g["goal"] == "Unit Quality")
    assert quality_goal["status"] == STATUS_RED


def test_assess_goal_progress_pipeline_volume() -> None:
    units = [_make_unit(unit_id=f"bu-{i}") for i in range(12)]
    goals = _assess_goal_progress(units)
    volume_goal = next(g for g in goals if g["goal"] == "Pipeline Volume")
    assert volume_goal["status"] == STATUS_GREEN


def test_assess_goal_progress_low_volume() -> None:
    units = [_make_unit()]
    goals = _assess_goal_progress(units)
    volume_goal = next(g for g in goals if g["goal"] == "Pipeline Volume")
    assert volume_goal["status"] == STATUS_RED


def test_assess_goal_progress_empty() -> None:
    goals = _assess_goal_progress([])
    assert goals == []


def test_assess_goal_progress_domain_coverage() -> None:
    units = [
        _make_unit(unit_id="bu-1", domain="devtools"),
        _make_unit(unit_id="bu-2", domain="security"),
        _make_unit(unit_id="bu-3", domain="analytics"),
    ]
    goals = _assess_goal_progress(units)
    domain_goal = next(g for g in goals if g["goal"] == "Domain Coverage")
    assert domain_goal["status"] == STATUS_GREEN


# ── Achievement tests ────────────────────────────────────────────────


def test_extract_achievements_high_quality() -> None:
    units = [_make_unit(quality_score=0.9)]
    achievements = _extract_achievements(units, [])
    assert any("high-quality" in a for a in achievements)


def test_extract_achievements_signals() -> None:
    signals = [_make_signal()]
    achievements = _extract_achievements([], signals)
    assert any("signal" in a.lower() for a in achievements)


def test_extract_achievements_empty() -> None:
    achievements = _extract_achievements([], [])
    assert achievements == []


# ── Priority tests ───────────────────────────────────────────────────


def test_extract_priorities_low_quality_units() -> None:
    units = [_make_unit(quality_score=0.2)]
    priorities = _extract_priorities(units, [])
    assert any("quality" in p.lower() or "improve" in p.lower() for p in priorities)


def test_extract_priorities_top_units() -> None:
    units = [_make_unit(quality_score=0.9, solution="Great Feature")]
    priorities = _extract_priorities(units, [])
    assert any("Great Feature" in p for p in priorities)


# ── Comparison tests ─────────────────────────────────────────────────


def test_build_quarter_comparisons() -> None:
    metrics = [
        {"name": "Signals", "value": 42, "trend": TREND_UP},
        {"name": "Units", "value": 10, "trend": TREND_FLAT},
    ]
    comparisons = _build_quarter_comparisons(metrics)
    assert len(comparisons) == 2
    assert comparisons[0]["metric"] == "Signals"
    assert comparisons[0]["current"] == "42"
    assert comparisons[0]["previous"] == "N/A"


# ── Rendering tests ─────────────────────────────────────────────────


def test_render_markdown_contains_sections() -> None:
    store = _mock_store(
        units=[_make_unit()],
        signals=[_make_signal()],
    )
    report = build_quarterly_review(store)
    md = render_quarterly_review_markdown(report)

    assert "# Quarterly Business Review" in md
    assert "## Key Metrics" in md
    assert "## Goal Progress" in md
    assert "## Key Achievements" in md
    assert "## Next Quarter Priorities" in md
    assert "## Quarter-over-Quarter Comparison" in md


def test_render_markdown_metric_table() -> None:
    store = _mock_store(
        units=[_make_unit()],
        signals=[_make_signal()],
    )
    report = build_quarterly_review(store)
    md = render_quarterly_review_markdown(report)
    assert "| Metric | Value | Trend |" in md


def test_render_markdown_empty() -> None:
    store = _mock_store()
    report = build_quarterly_review(store)
    md = render_quarterly_review_markdown(report)
    assert "# Quarterly Business Review" in md


def test_render_json_valid() -> None:
    store = _mock_store()
    report = build_quarterly_review(store)
    parsed = json.loads(render_quarterly_review_json(report))
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND


def test_render_json_roundtrip() -> None:
    store = _mock_store(
        units=[_make_unit()],
        signals=[_make_signal()],
    )
    report = build_quarterly_review(store)
    parsed = json.loads(render_quarterly_review_json(report))
    assert len(parsed["metrics"]) >= 2
    assert "quarter" in parsed
