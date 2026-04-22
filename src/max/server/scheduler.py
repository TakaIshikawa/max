"""Pipeline scheduler — runs idea generation on a configurable interval."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from max.focus import focused_profile_names
from max.llm.client import BudgetExceededError
from max.pipeline.runner import PipelineResult, run_pipeline
from max.profiles.loader import load_profile

logger = logging.getLogger(__name__)

PIPELINE_PROFILE_OVERRIDE_KEYS = {
    "signal_limit",
    "min_score",
    "weight_profile",
    "ideation_mode",
    "quality_loop_enabled",
}


class Scheduler:
    """Asyncio background task that runs the pipeline on a schedule."""

    def __init__(
        self,
        *,
        interval_seconds: int = 21600,
        enabled: bool = True,
        profile: str | None = None,
        include_all: bool = False,
        pipeline_kwargs: dict | None = None,
        max_consecutive_failures: int = 3,
        max_execution_seconds: int = 1800,
    ):
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self.profile = profile
        self.include_all = include_all
        self.pipeline_kwargs = pipeline_kwargs or {}
        self.max_consecutive_failures = max_consecutive_failures
        self.max_execution_seconds = max_execution_seconds
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
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._run_pipeline),
                    timeout=self.max_execution_seconds,
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
            except asyncio.TimeoutError:
                self.last_error = f"Pipeline execution timeout after {self.max_execution_seconds}s"
                self.last_error_at = datetime.now(UTC)
                self._failure_streak += 1
                logger.error(
                    "Scheduled pipeline run timed out after %ds",
                    self.max_execution_seconds,
                )
                if self._failure_streak >= self.max_consecutive_failures:
                    self.enabled = False
                    logger.error(
                        "Scheduler paused after %d consecutive failures",
                        self._failure_streak,
                    )
                return None
            except BudgetExceededError as exc:
                self.last_error = str(exc)
                self.last_error_at = datetime.now(UTC)
                self._failure_streak += 1
                self.enabled = False
                logger.error("Scheduler paused: token/cost budget exceeded")
                return None
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

    def _run_pipeline(self) -> PipelineResult:
        """Run the pipeline using the currently configured schedule profile."""
        if self.profile == "all":
            return self._run_all_profiles()
        return run_pipeline(**self._pipeline_run_kwargs())

    def _pipeline_run_kwargs(self, profile_name: str | None = None) -> dict:
        kwargs = dict(self.pipeline_kwargs)
        resolved_profile_name = profile_name or self.profile
        if resolved_profile_name:
            profile = load_profile(resolved_profile_name).model_copy(deep=True)
            self._apply_pipeline_overrides(profile, kwargs)
            kwargs = {
                key: value
                for key, value in kwargs.items()
                if key not in PIPELINE_PROFILE_OVERRIDE_KEYS
            }
            kwargs["profile"] = profile
        return kwargs

    def _run_all_profiles(self) -> PipelineResult:
        profile_names, _, focus_domains = focused_profile_names(
            include_all=self.include_all
        )
        if not profile_names:
            if focus_domains is None:
                raise RuntimeError("No profiles found")
            raise RuntimeError(
                "No profiles match focus. Clear focus or set include_all=true."
            )

        results = [
            run_pipeline(**self._pipeline_run_kwargs(profile_name))
            for profile_name in profile_names
        ]
        return self._aggregate_results(results)

    @staticmethod
    def _apply_pipeline_overrides(profile, kwargs: dict) -> None:
        if "signal_limit" in kwargs:
            profile.signal_limit = kwargs["signal_limit"]
        if "min_score" in kwargs:
            profile.evaluation.min_score = kwargs["min_score"]
        if "weight_profile" in kwargs:
            profile.evaluation.weight_profile = kwargs["weight_profile"]
        if "ideation_mode" in kwargs:
            profile.ideation_mode = kwargs["ideation_mode"]
        if "quality_loop_enabled" in kwargs:
            profile.quality_loop_enabled = kwargs["quality_loop_enabled"]

    @staticmethod
    def _aggregate_results(results: list[PipelineResult]) -> PipelineResult:
        aggregate = PipelineResult(profile_name="all")
        if not results:
            return aggregate

        for result in results:
            aggregate.signals_fetched += result.signals_fetched
            aggregate.signals_new += result.signals_new
            aggregate.insights_generated += result.insights_generated
            aggregate.ideas_generated += result.ideas_generated
            aggregate.ideas_evaluated += result.ideas_evaluated
            aggregate.top_ideas.extend(result.top_ideas)
            aggregate.draft_ideas_generated += result.draft_ideas_generated
            aggregate.ideas_revised += result.ideas_revised
            aggregate.ideas_rejected_by_quality_gate += result.ideas_rejected_by_quality_gate
            aggregate.ideas_rejected_by_domain_quality += result.ideas_rejected_by_domain_quality
            for key, value in result.token_usage.items():
                aggregate.token_usage[key] = aggregate.token_usage.get(key, 0) + value

        aggregate.avg_insight_confidence = sum(
            result.avg_insight_confidence * result.insights_generated
            for result in results
        ) / max(aggregate.insights_generated, 1)
        aggregate.avg_idea_score = sum(
            result.avg_idea_score * result.ideas_evaluated
            for result in results
        ) / max(aggregate.ideas_evaluated, 1)
        return aggregate

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
                "avg_insight_confidence": self.last_result.avg_insight_confidence,
                "avg_idea_score": self.last_result.avg_idea_score,
            }

        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "profile": self.profile,
            "include_all": self.include_all,
            "max_execution_seconds": self.max_execution_seconds,
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
        profile: str | None = None,
        include_all: bool | None = None,
        signal_limit: int | None = None,
        min_score: float | None = None,
        weight_profile: str | None = None,
        ideation_mode: str | None = None,
        quality_loop_enabled: bool | None = None,
        max_consecutive_failures: int | None = None,
        max_execution_seconds: int | None = None,
    ) -> None:
        """Update schedule configuration at runtime."""
        if enabled is not None:
            self.enabled = enabled
        if interval_seconds is not None:
            self.interval_seconds = interval_seconds
        if profile is not None:
            self.profile = profile
        if include_all is not None:
            self.include_all = include_all
        if signal_limit is not None:
            self.pipeline_kwargs["signal_limit"] = signal_limit
        if min_score is not None:
            self.pipeline_kwargs["min_score"] = min_score
        if weight_profile is not None:
            self.pipeline_kwargs["weight_profile"] = weight_profile
        if ideation_mode is not None:
            self.pipeline_kwargs["ideation_mode"] = ideation_mode
        if quality_loop_enabled is not None:
            self.pipeline_kwargs["quality_loop_enabled"] = quality_loop_enabled
        if max_consecutive_failures is not None:
            self.max_consecutive_failures = max_consecutive_failures
        if max_execution_seconds is not None:
            self.max_execution_seconds = max_execution_seconds

    def resume(self) -> None:
        """Resume the scheduler after auto-pause, resetting failure counter."""
        self._failure_streak = 0
        self.enabled = True
        logger.info("Scheduler resumed — failure streak reset")

    def reset_and_resume(self, new_config: dict | None = None) -> None:
        """Reset failure state and optionally update config, then resume.

        Args:
            new_config: Optional dict of config parameters to update.
                       Accepts all parameters from update() method.
        """
        self._failure_streak = 0
        self.last_error = None
        self.last_error_at = None

        if new_config:
            self.update(**new_config)

        self.enabled = True
        logger.info("Scheduler reset and resumed — failure state cleared")
