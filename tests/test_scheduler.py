"""Tests for the pipeline scheduler."""

from __future__ import annotations

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


def test_scheduler_status():
    scheduler = Scheduler(interval_seconds=3600, enabled=False)
    status = scheduler.status()
    assert status["enabled"] is False
    assert status["interval_seconds"] == 3600
    assert status["running"] is False
    assert status["run_count"] == 0
    assert status["last_run_at"] is None
    assert status["last_result"] is None


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


@pytest.mark.asyncio
async def test_scheduler_run_once_skips_if_running():
    scheduler = Scheduler(interval_seconds=60, enabled=True)
    scheduler._running = True

    result = await scheduler.run_once()
    assert result is None
    assert scheduler.run_count == 0


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
