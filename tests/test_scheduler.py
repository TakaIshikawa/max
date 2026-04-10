"""Tests for the pipeline scheduler."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from max.server.scheduler import Scheduler


@pytest.fixture
def mock_pipeline_result():
    """A mock PipelineResult."""
    from max.pipeline.runner import PipelineResult

    return PipelineResult(
        signals_fetched=10,
        signals_new=3,
        insights_generated=2,
        ideas_generated=2,
        ideas_evaluated=2,
        specs_generated=1,
        avg_insight_confidence=0.75,
        avg_idea_score=65.0,
    )


def test_scheduler_init():
    scheduler = Scheduler(
        interval_seconds=60,
        enabled=True,
        pipeline_kwargs={"signal_limit": 10},
    )
    assert scheduler.interval_seconds == 60
    assert scheduler.enabled is True
    assert scheduler.pipeline_kwargs == {"signal_limit": 10}
    assert scheduler.run_count == 0
    assert scheduler.last_run_at is None
    assert scheduler.last_result is None
    assert scheduler._failure_streak == 0
    assert scheduler.max_consecutive_failures == 3
    assert scheduler.last_error_at is None


def test_scheduler_status():
    scheduler = Scheduler(interval_seconds=3600, enabled=False)
    status = scheduler.status()
    assert status["enabled"] is False
    assert status["interval_seconds"] == 3600
    assert status["running"] is False
    assert status["run_count"] == 0
    assert status["last_run_at"] is None
    assert status["last_result"] is None
    assert status["failure_streak"] == 0
    assert status["max_consecutive_failures"] == 3
    assert status["last_error_at"] is None


def test_scheduler_update():
    scheduler = Scheduler(
        interval_seconds=60,
        enabled=True,
        pipeline_kwargs={"signal_limit": 10, "min_score": 50.0},
    )
    scheduler.update(enabled=False, interval_seconds=120, signal_limit=20)
    assert scheduler.enabled is False
    assert scheduler.interval_seconds == 120
    assert scheduler.pipeline_kwargs["signal_limit"] == 20
    assert scheduler.pipeline_kwargs["min_score"] == 50.0  # unchanged


def test_scheduler_update_partial():
    scheduler = Scheduler(interval_seconds=60, enabled=True)
    scheduler.update(enabled=False)
    assert scheduler.enabled is False
    assert scheduler.interval_seconds == 60  # unchanged


def test_status_initial_state():
    """Comprehensive status check for a new scheduler with all fields."""
    scheduler = Scheduler(
        interval_seconds=7200,
        enabled=True,
        pipeline_kwargs={"signal_limit": 25, "min_score": 60.0},
        max_consecutive_failures=5,
    )
    status = scheduler.status()

    assert status["enabled"] is True
    assert status["interval_seconds"] == 7200
    assert status["running"] is False
    assert status["last_run_at"] is None
    assert status["next_run_at"] is None
    assert status["run_count"] == 0
    assert status["last_error"] is None
    assert status["last_error_at"] is None
    assert status["failure_streak"] == 0
    assert status["max_consecutive_failures"] == 5
    assert status["last_result"] is None
    assert status["pipeline_config"] == {"signal_limit": 25, "min_score": 60.0}


def test_update_enabled():
    """Test toggling enabled flag via update()."""
    scheduler = Scheduler(interval_seconds=60, enabled=True)
    assert scheduler.enabled is True

    scheduler.update(enabled=False)
    assert scheduler.enabled is False

    scheduler.update(enabled=True)
    assert scheduler.enabled is True


def test_update_interval():
    """Test updating interval_seconds via update()."""
    scheduler = Scheduler(interval_seconds=60, enabled=True)
    assert scheduler.interval_seconds == 60

    scheduler.update(interval_seconds=3600)
    assert scheduler.interval_seconds == 3600


def test_update_pipeline_kwargs():
    """Test updating pipeline configuration parameters."""
    scheduler = Scheduler(
        interval_seconds=60,
        enabled=True,
        pipeline_kwargs={"signal_limit": 30},
    )
    assert scheduler.pipeline_kwargs == {"signal_limit": 30}

    scheduler.update(signal_limit=50, min_score=70.0)
    assert scheduler.pipeline_kwargs["signal_limit"] == 50
    assert scheduler.pipeline_kwargs["min_score"] == 70.0


def test_update_max_consecutive_failures():
    """Test updating max_consecutive_failures via update()."""
    scheduler = Scheduler(interval_seconds=60, enabled=True)
    assert scheduler.max_consecutive_failures == 3

    scheduler.update(max_consecutive_failures=5)
    assert scheduler.max_consecutive_failures == 5


def test_update_partial_does_not_reset_others():
    """Partial update preserves unchanged fields."""
    scheduler = Scheduler(
        interval_seconds=60,
        enabled=True,
        pipeline_kwargs={"signal_limit": 30, "min_score": 50.0},
        max_consecutive_failures=3,
    )

    scheduler.update(enabled=False)

    assert scheduler.enabled is False
    assert scheduler.interval_seconds == 60
    assert scheduler.pipeline_kwargs == {"signal_limit": 30, "min_score": 50.0}
    assert scheduler.max_consecutive_failures == 3


def test_update_all_pipeline_kwargs():
    """Test updating all supported pipeline kwargs."""
    scheduler = Scheduler(interval_seconds=60, enabled=True)

    scheduler.update(
        signal_limit=100,
        min_score=75.0,
        weight_profile="balanced",
        ideation_mode="creative",
    )

    assert scheduler.pipeline_kwargs["signal_limit"] == 100
    assert scheduler.pipeline_kwargs["min_score"] == 75.0
    assert scheduler.pipeline_kwargs["weight_profile"] == "balanced"
    assert scheduler.pipeline_kwargs["ideation_mode"] == "creative"


@pytest.mark.asyncio
async def test_scheduler_run_once(mock_pipeline_result):
    scheduler = Scheduler(interval_seconds=60, enabled=True)

    with patch("max.server.scheduler.run_pipeline", return_value=mock_pipeline_result):
        result = await scheduler.run_once()

    assert result is not None
    assert result.signals_fetched == 10
    assert scheduler.run_count == 1
    assert scheduler.last_run_at is not None
    assert scheduler.last_result is mock_pipeline_result
    assert scheduler.last_error is None


@pytest.mark.asyncio
async def test_scheduler_run_once_failure():
    scheduler = Scheduler(interval_seconds=60, enabled=True)

    with patch("max.server.scheduler.run_pipeline", side_effect=RuntimeError("API down")):
        result = await scheduler.run_once()

    assert result is None
    assert scheduler.run_count == 0
    assert scheduler.last_error == "API down"
    assert scheduler.last_error_at is not None
    assert scheduler._failure_streak == 1


@pytest.mark.asyncio
async def test_scheduler_run_once_skips_if_running():
    scheduler = Scheduler(interval_seconds=60, enabled=True)
    # Acquire the lock to simulate an in-progress run
    await scheduler._lock.acquire()

    result = await scheduler.run_once()
    assert result is None
    assert scheduler.run_count == 0

    scheduler._lock.release()


@pytest.mark.asyncio
async def test_scheduler_start_stop():
    scheduler = Scheduler(interval_seconds=999, enabled=False)
    await scheduler.start()
    assert scheduler._task is not None
    assert not scheduler._task.done()

    await scheduler.stop()
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_scheduler_status_after_run(mock_pipeline_result):
    scheduler = Scheduler(
        interval_seconds=60,
        enabled=True,
        pipeline_kwargs={"signal_limit": 30, "min_score": 50.0},
    )

    with patch("max.server.scheduler.run_pipeline", return_value=mock_pipeline_result):
        await scheduler.run_once()

    status = scheduler.status()
    assert status["run_count"] == 1
    assert status["last_run_at"] is not None
    assert status["last_result"]["signals_fetched"] == 10
    assert status["last_result"]["ideas_generated"] == 2
    assert status["pipeline_config"]["signal_limit"] == 30
    assert status["failure_streak"] == 0


@pytest.mark.asyncio
async def test_concurrent_run_prevention(mock_pipeline_result):
    """Second trigger is skipped while first run is in-progress."""
    scheduler = Scheduler(interval_seconds=60, enabled=True)
    started = asyncio.Event()
    proceed = asyncio.Event()

    original_run_pipeline = None

    def slow_pipeline(**kwargs):
        started.set()
        # Block until the test signals to proceed (run in thread, so use
        # a threading event wrapped via asyncio).
        import threading

        barrier = threading.Event()
        # Stash on scheduler so the test can release it
        scheduler._test_barrier = barrier
        barrier.wait(timeout=5)
        return mock_pipeline_result

    with patch("max.server.scheduler.run_pipeline", side_effect=slow_pipeline):
        # Start the first run (will block inside slow_pipeline)
        task1 = asyncio.create_task(scheduler.run_once())

        # Wait until slow_pipeline is actually executing
        await asyncio.sleep(0.05)

        # Attempt a second concurrent run — should be skipped
        result2 = await scheduler.run_once()
        assert result2 is None

        # Release the first run
        scheduler._test_barrier.set()
        result1 = await task1

    assert result1 is not None
    assert scheduler.run_count == 1


@pytest.mark.asyncio
async def test_error_tracking_after_failure():
    """Failed pipeline run stores error message and timestamp."""
    scheduler = Scheduler(interval_seconds=60, enabled=True)

    with patch(
        "max.server.scheduler.run_pipeline",
        side_effect=ValueError("bad config"),
    ):
        await scheduler.run_once()

    assert scheduler.last_error == "bad config"
    assert scheduler.last_error_at is not None
    assert scheduler._failure_streak == 1
    status = scheduler.status()
    assert status["last_error"] == "bad config"
    assert status["last_error_at"] is not None
    assert status["failure_streak"] == 1


@pytest.mark.asyncio
async def test_auto_pause_after_max_consecutive_failures():
    """Scheduler disables itself after N consecutive failures."""
    scheduler = Scheduler(
        interval_seconds=60, enabled=True, max_consecutive_failures=2
    )

    with patch(
        "max.server.scheduler.run_pipeline",
        side_effect=RuntimeError("fail"),
    ):
        await scheduler.run_once()  # failure 1
        assert scheduler.enabled is True
        assert scheduler._failure_streak == 1

        await scheduler.run_once()  # failure 2 — triggers pause
        assert scheduler.enabled is False
        assert scheduler._failure_streak == 2


@pytest.mark.asyncio
async def test_failure_streak_resets_on_success(mock_pipeline_result):
    """Successful run resets the failure streak to zero."""
    scheduler = Scheduler(interval_seconds=60, enabled=True)

    with patch(
        "max.server.scheduler.run_pipeline",
        side_effect=RuntimeError("fail"),
    ):
        await scheduler.run_once()
        await scheduler.run_once()

    assert scheduler._failure_streak == 2

    with patch(
        "max.server.scheduler.run_pipeline",
        return_value=mock_pipeline_result,
    ):
        await scheduler.run_once()

    assert scheduler._failure_streak == 0
    assert scheduler.run_count == 1


@pytest.mark.asyncio
async def test_status_shows_run_count_and_failure_streak(mock_pipeline_result):
    """Status endpoint exposes run_count and failure_streak."""
    scheduler = Scheduler(interval_seconds=60, enabled=True)

    with patch(
        "max.server.scheduler.run_pipeline",
        return_value=mock_pipeline_result,
    ):
        await scheduler.run_once()
        await scheduler.run_once()

    status = scheduler.status()
    assert status["run_count"] == 2
    assert status["failure_streak"] == 0

    with patch(
        "max.server.scheduler.run_pipeline",
        side_effect=RuntimeError("oops"),
    ):
        await scheduler.run_once()

    status = scheduler.status()
    assert status["run_count"] == 2
    assert status["failure_streak"] == 1
