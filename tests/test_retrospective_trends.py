"""Tests for detect_trends() — approval rate trend detection over pipeline windows."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from click.testing import CliRunner

from max.analysis.retrospective import detect_trends
from max.cli import main
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType
from max.types.trends import TrendPoint


def _make_score(value: float = 7.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _insert_run(store: Store, run_id: str, started: str, completed: str, signals: int = 10) -> None:
    """Insert a pipeline run with given timestamps."""
    store.conn.execute(
        "INSERT INTO pipeline_runs (id, started_at, config) VALUES (?, ?, ?)",
        (run_id, started, json.dumps({"profile": "test"})),
    )
    store.conn.execute(
        """UPDATE pipeline_runs SET
           completed_at = ?,
           signals_fetched = ?, signals_new = ?,
           insights_generated = 0, ideas_generated = 0,
           ideas_evaluated = 0, specs_generated = 0,
           clusters_found = 0, gaps_detected = 0,
           avg_idea_score = 0.0,
           fetch_allocation = '{}', token_usage = '{}',
           adapter_metrics = '{}'
           WHERE id = ?""",
        (completed, signals, signals, run_id),
    )
    store.conn.commit()


def _seed_feedback_at(
    store: Store,
    unit_id: str,
    outcome: str,
    created_at: str,
    *,
    eval_score: float = 70.0,
) -> None:
    """Seed a signal + unit + evaluation + feedback at a specific timestamp."""
    sig_id = f"sig-{unit_id}"
    sig = Signal(
        id=sig_id,
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title=f"Signal for {unit_id}",
        content="Test content",
        url=f"https://example.com/{sig_id}",
        credibility=0.7,
        metadata={"signal_role": "problem"},
    )
    store.insert_signal(sig)

    unit = BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="Test",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        value_proposition="Test value",
        evidence_signals=[sig_id],
        target_users="both",
    )
    store.insert_buildable_unit(unit)

    evaluation = UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_make_score(8.0),
        addressable_scale=_make_score(7.0),
        build_effort=_make_score(6.0),
        composability=_make_score(7.5),
        competitive_density=_make_score(8.0),
        timing_fit=_make_score(7.0),
        compounding_value=_make_score(6.5),
        overall_score=eval_score,
        strengths=["test"],
        weaknesses=["test"],
        recommendation="yes" if outcome == "approved" else "no",
        weights_used={"pain_severity": 0.2},
    )
    store.insert_evaluation(evaluation)

    # Insert feedback with explicit created_at timestamp.
    dimension_values = {
        "pain_severity": 8.0,
        "addressable_scale": 7.0,
        "build_effort": 6.0,
        "composability": 7.5,
        "competitive_density": 8.0,
        "timing_fit": 7.0,
        "compounding_value": 6.5,
    }
    store.conn.execute(
        """INSERT INTO feedback
           (buildable_unit_id, outcome, reason, dimension_values, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (unit_id, outcome, "", json.dumps(dimension_values), created_at),
    )
    store.conn.commit()


def _base_time() -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ── Insufficient data ────────────────────────────────────────────


def test_no_runs_returns_empty(store: Store) -> None:
    assert detect_trends(store) == []


def test_fewer_runs_than_window_returns_empty(store: Store) -> None:
    base = _base_time()
    for i in range(3):
        t = base + timedelta(hours=i)
        _insert_run(store, f"run-{i}", _iso(t), _iso(t + timedelta(minutes=30)))
    assert detect_trends(store, window=5) == []


# ── Single window ────────────────────────────────────────────────


def test_single_window_stable(store: Store) -> None:
    """A single window with mixed feedback should be 'stable' (no prior to compare)."""
    base = _base_time()
    for i in range(5):
        t = base + timedelta(hours=i)
        _insert_run(store, f"run-{i}", _iso(t), _iso(t + timedelta(minutes=30)))

    # 3 approved, 2 rejected within window range.
    for i in range(3):
        t = base + timedelta(hours=i, minutes=10)
        _seed_feedback_at(store, f"bu-a-{i}", "approved", _iso(t), eval_score=80.0)
    for i in range(2):
        t = base + timedelta(hours=3 + i, minutes=10)
        _seed_feedback_at(store, f"bu-r-{i}", "rejected", _iso(t), eval_score=40.0)

    points = detect_trends(store, window=5)
    assert len(points) == 1

    pt = points[0]
    assert pt.trend_direction == "stable"
    assert pt.approval_rate == 0.6  # 3/5
    assert pt.avg_score == 64.0  # (80*3 + 40*2) / 5
    assert pt.signal_count == 50  # 5 runs * 10 signals


# ── Two windows — improving ──────────────────────────────────────


def test_two_windows_improving(store: Store) -> None:
    """When second window has higher approval rate, trend should be 'improving'."""
    base = _base_time()

    # Window 1: runs 0-4.
    for i in range(5):
        t = base + timedelta(hours=i)
        _insert_run(store, f"run-w1-{i}", _iso(t), _iso(t + timedelta(minutes=30)))

    # Window 2: runs 5-9.
    for i in range(5):
        t = base + timedelta(hours=10 + i)
        _insert_run(store, f"run-w2-{i}", _iso(t), _iso(t + timedelta(minutes=30)))

    # Window 1 feedback: 1 approved, 4 rejected → 20%.
    for i in range(1):
        t = base + timedelta(hours=i, minutes=10)
        _seed_feedback_at(store, f"bu-w1a-{i}", "approved", _iso(t))
    for i in range(4):
        t = base + timedelta(hours=1 + i, minutes=10)
        _seed_feedback_at(store, f"bu-w1r-{i}", "rejected", _iso(t))

    # Window 2 feedback: 4 approved, 1 rejected → 80%.
    for i in range(4):
        t = base + timedelta(hours=10 + i, minutes=10)
        _seed_feedback_at(store, f"bu-w2a-{i}", "approved", _iso(t))
    for i in range(1):
        t = base + timedelta(hours=14, minutes=10)
        _seed_feedback_at(store, f"bu-w2r-{i}", "rejected", _iso(t))

    points = detect_trends(store, window=5)
    assert len(points) == 2
    assert points[0].trend_direction == "stable"  # First window, no prior.
    assert points[0].approval_rate == 0.2
    assert points[1].trend_direction == "improving"
    assert points[1].approval_rate == 0.8


# ── Two windows — declining ──────────────────────────────────────


def test_two_windows_declining(store: Store) -> None:
    """When second window has lower approval rate, trend should be 'declining'."""
    base = _base_time()

    for i in range(5):
        t = base + timedelta(hours=i)
        _insert_run(store, f"run-w1-{i}", _iso(t), _iso(t + timedelta(minutes=30)))
    for i in range(5):
        t = base + timedelta(hours=10 + i)
        _insert_run(store, f"run-w2-{i}", _iso(t), _iso(t + timedelta(minutes=30)))

    # Window 1: 4 approved, 1 rejected → 80%.
    for i in range(4):
        t = base + timedelta(hours=i, minutes=10)
        _seed_feedback_at(store, f"bu-w1a-{i}", "approved", _iso(t))
    _seed_feedback_at(
        store, "bu-w1r-0", "rejected",
        _iso(base + timedelta(hours=4, minutes=10)),
    )

    # Window 2: 1 approved, 4 rejected → 20%.
    _seed_feedback_at(
        store, "bu-w2a-0", "approved",
        _iso(base + timedelta(hours=10, minutes=10)),
    )
    for i in range(4):
        t = base + timedelta(hours=11 + i, minutes=10)
        _seed_feedback_at(store, f"bu-w2r-{i}", "rejected", _iso(t))

    points = detect_trends(store, window=5)
    assert len(points) == 2
    assert points[1].trend_direction == "declining"
    assert points[1].approval_rate == 0.2


# ── Stable within threshold ──────────────────────────────────────


def test_two_windows_stable_within_threshold(store: Store) -> None:
    """Windows with <5% delta should be 'stable'."""
    base = _base_time()

    for i in range(10):
        t = base + timedelta(hours=i)
        _insert_run(store, f"run-{i}", _iso(t), _iso(t + timedelta(minutes=30)))

    # Window 1: 3 approved, 2 rejected → 60%.
    for i in range(3):
        t = base + timedelta(hours=i, minutes=10)
        _seed_feedback_at(store, f"bu-w1a-{i}", "approved", _iso(t))
    for i in range(2):
        t = base + timedelta(hours=3 + i, minutes=10)
        _seed_feedback_at(store, f"bu-w1r-{i}", "rejected", _iso(t))

    # Window 2: 3 approved, 2 rejected → 60% (same).
    for i in range(3):
        t = base + timedelta(hours=5 + i, minutes=10)
        _seed_feedback_at(store, f"bu-w2a-{i}", "approved", _iso(t))
    for i in range(2):
        t = base + timedelta(hours=8 + i, minutes=10)
        _seed_feedback_at(store, f"bu-w2r-{i}", "rejected", _iso(t))

    points = detect_trends(store, window=5)
    assert len(points) == 2
    assert points[1].trend_direction == "stable"


# ── No feedback in window ────────────────────────────────────────


def test_window_with_no_feedback(store: Store) -> None:
    """A window with no feedback should have 0 approval_rate and 0 avg_score."""
    base = _base_time()
    for i in range(5):
        t = base + timedelta(hours=i)
        _insert_run(store, f"run-{i}", _iso(t), _iso(t + timedelta(minutes=30)))

    points = detect_trends(store, window=5)
    assert len(points) == 1
    assert points[0].approval_rate == 0.0
    assert points[0].avg_score == 0.0


# ── Signal count aggregation ────────────────────────────────────


def test_signal_count_sums_across_window(store: Store) -> None:
    """signal_count should sum signals_fetched across all runs in the window."""
    base = _base_time()
    for i in range(5):
        t = base + timedelta(hours=i)
        _insert_run(store, f"run-{i}", _iso(t), _iso(t + timedelta(minutes=30)), signals=i + 1)

    points = detect_trends(store, window=5)
    assert len(points) == 1
    assert points[0].signal_count == 15  # 1+2+3+4+5


# ── Custom window size ───────────────────────────────────────────


def test_custom_window_size(store: Store) -> None:
    """Window size of 2 should create more granular windows."""
    base = _base_time()
    for i in range(4):
        t = base + timedelta(hours=i)
        _insert_run(store, f"run-{i}", _iso(t), _iso(t + timedelta(minutes=30)))

    points = detect_trends(store, window=2)
    assert len(points) == 2


# ── TrendPoint dataclass ────────────────────────────────────────


def test_trend_point_fields() -> None:
    """TrendPoint should have all specified fields."""
    pt = TrendPoint(
        window_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        window_end=datetime(2025, 1, 2, tzinfo=timezone.utc),
        approval_rate=0.75,
        avg_score=65.0,
        signal_count=42,
        trend_direction="improving",
    )
    assert pt.approval_rate == 0.75
    assert pt.avg_score == 65.0
    assert pt.signal_count == 42
    assert pt.trend_direction == "improving"


# ── Published counts as approved ─────────────────────────────────


def test_published_counts_as_approved(store: Store) -> None:
    """'published' outcome should count toward approval rate."""
    base = _base_time()
    for i in range(5):
        t = base + timedelta(hours=i)
        _insert_run(store, f"run-{i}", _iso(t), _iso(t + timedelta(minutes=30)))

    # 2 published, 1 rejected → 66.7%.
    for i in range(2):
        t = base + timedelta(hours=i, minutes=10)
        _seed_feedback_at(store, f"bu-pub-{i}", "published", _iso(t))
    _seed_feedback_at(
        store, "bu-rej-0", "rejected",
        _iso(base + timedelta(hours=2, minutes=10)),
    )

    points = detect_trends(store, window=5)
    assert len(points) == 1
    assert abs(points[0].approval_rate - 2 / 3) < 0.01


# ── CLI command ──────────────────────────────────────────────────


def test_cli_trends_no_data(store: Store, monkeypatch) -> None:
    """CLI should show a message when there are not enough runs."""
    monkeypatch.setattr("max.store.db.Store", lambda: store)

    runner = CliRunner()
    result = runner.invoke(main, ["trends"])
    assert result.exit_code == 0
    assert "Not enough pipeline runs" in result.output


def test_cli_trends_with_data(store: Store, monkeypatch) -> None:
    """CLI should display a formatted table when trends are available."""
    monkeypatch.setattr("max.store.db.Store", lambda: store)

    base = _base_time()
    for i in range(5):
        t = base + timedelta(hours=i)
        _insert_run(store, f"run-{i}", _iso(t), _iso(t + timedelta(minutes=30)))

    for i in range(3):
        t = base + timedelta(hours=i, minutes=10)
        _seed_feedback_at(store, f"bu-cli-a-{i}", "approved", _iso(t))
    for i in range(2):
        t = base + timedelta(hours=3 + i, minutes=10)
        _seed_feedback_at(store, f"bu-cli-r-{i}", "rejected", _iso(t))

    runner = CliRunner()
    result = runner.invoke(main, ["trends"])
    assert result.exit_code == 0
    assert "Approval" in result.output
    assert "Trend" in result.output
    assert "60.0%" in result.output
