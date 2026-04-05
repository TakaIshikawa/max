"""Pipeline scheduler — runs idea generation on a configurable interval."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from max.pipeline.runner import PipelineResult, run_pipeline

logger = logging.getLogger(__name__)


class Scheduler:
    """Asyncio background task that runs the pipeline on a schedule."""

    def __init__(
        self,
        *,
        interval_seconds: int = 21600,
        enabled: bool = True,
        pipeline_kwargs: dict | None = None,
        max_consecutive_failures: int = 3,
    ):
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self.pipeline_kwargs = pipeline_kwargs or {}
        self.max_consecutive_failures = max_consecutive_failures
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self.last_run_at: datetime | None = None
        self.last_result: PipelineResult | None = None
        self.next_run_at: datetime | None = None
        self.run_count: int = 0
        self.last_error: str | None = None
        self.last_error_at: datetime | None = None
        self._failure_streak: int = 0

    async def start(self) -> None:
        """Start the background scheduler loop."""
        self._task = asyncio.create_task(self._loop())
        state = "enabled" if self.enabled else "disabled"
        logger.info(
            "Scheduler started (%s, interval: %ds)", state, self.interval_seconds
        )

    async def stop(self) -> None:
        """Stop the background scheduler loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Scheduler stopped")

    async def _loop(self) -> None:
        """Main loop: sleep → run → repeat."""
        while True:
            self.next_run_at = datetime.now(UTC) + timedelta(
                seconds=self.interval_seconds
            )
            await asyncio.sleep(self.interval_seconds)
            if self.enabled:
                await self.run_once()

    async def run_once(self) -> PipelineResult | None:
        """Execute the pipeline once in a thread."""
        if self._lock.locked():
            logger.warning("Pipeline already running, skipping")
            return None

        async with self._lock:
            self.last_error = None
            try:
                result = await asyncio.to_thread(
                    run_pipeline, **self.pipeline_kwargs
                )
                self.last_result = result
                self.last_run_at = datetime.now(UTC)
                self.run_count += 1
                self._failure_streak = 0
                logger.info(
                    "Pipeline run #%d complete: %d signals, %d insights, %d ideas (avg score: %.1f)",
                    self.run_count,
                    result.signals_fetched,
                    result.insights_generated,
                    result.ideas_generated,
                    result.avg_idea_score,
                )
                return result
            except Exception as exc:
                self.last_error = str(exc)
                self.last_error_at = datetime.now(UTC)
                self._failure_streak += 1
                logger.exception("Scheduled pipeline run failed")
                if self._failure_streak >= self.max_consecutive_failures:
                    self.enabled = False
                    logger.error(
                        "Scheduler paused after %d consecutive failures",
                        self._failure_streak,
                    )
                return None

    def status(self) -> dict:
        """Return current schedule state."""
        last_result_summary = None
        if self.last_result:
            last_result_summary = {
                "signals_fetched": self.last_result.signals_fetched,
                "signals_new": self.last_result.signals_new,
                "insights_generated": self.last_result.insights_generated,
                "ideas_generated": self.last_result.ideas_generated,
                "ideas_evaluated": self.last_result.ideas_evaluated,
                "specs_generated": self.last_result.specs_generated,
                "avg_insight_confidence": self.last_result.avg_insight_confidence,
                "avg_idea_score": self.last_result.avg_idea_score,
            }

        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "running": self._lock.locked(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "run_count": self.run_count,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at.isoformat() if self.last_error_at else None,
            "failure_streak": self._failure_streak,
            "max_consecutive_failures": self.max_consecutive_failures,
            "last_result": last_result_summary,
            "pipeline_config": self.pipeline_kwargs,
        }

    def update(
        self,
        *,
        enabled: bool | None = None,
        interval_seconds: int | None = None,
        signal_limit: int | None = None,
        min_score: float | None = None,
        weight_profile: str | None = None,
        ideation_mode: str | None = None,
        max_consecutive_failures: int | None = None,
    ) -> None:
        """Update schedule configuration at runtime."""
        if enabled is not None:
            self.enabled = enabled
        if interval_seconds is not None:
            self.interval_seconds = interval_seconds
        if signal_limit is not None:
            self.pipeline_kwargs["signal_limit"] = signal_limit
        if min_score is not None:
            self.pipeline_kwargs["min_score"] = min_score
        if weight_profile is not None:
            self.pipeline_kwargs["weight_profile"] = weight_profile
        if ideation_mode is not None:
            self.pipeline_kwargs["ideation_mode"] = ideation_mode
        if max_consecutive_failures is not None:
            self.max_consecutive_failures = max_consecutive_failures
