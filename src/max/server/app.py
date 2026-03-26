"""App factory — creates FastAPI app with MCP server and scheduler."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from max.server.api import router
from max.server.mcp_tools import create_mcp_server, set_scheduler_ref
from max.server.scheduler import Scheduler

logger = logging.getLogger(__name__)


def _get_schedule_config() -> dict:
    """Read schedule config fresh from env (supports CLI overrides)."""
    return {
        "interval_seconds": int(os.getenv("MAX_SCHEDULE_INTERVAL", "21600")),
        "enabled": os.getenv("MAX_SCHEDULE_ENABLED", "true").lower() == "true",
        "signal_limit": int(os.getenv("MAX_SCHEDULE_SIGNAL_LIMIT", "30")),
        "min_score": float(os.getenv("MAX_SCHEDULE_MIN_SCORE", "50.0")),
        "weight_profile": os.getenv("MAX_SCHEDULE_PROFILE", "default"),
        "ideation_mode": os.getenv("MAX_SCHEDULE_MODE", "direct"),
    }


def create_app() -> FastAPI:
    """Create the combined FastAPI + MCP + Scheduler application."""
    mcp = create_mcp_server()
    mcp_app = mcp.http_app(path="/mcp")
    mcp_lifespan = mcp_app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp_lifespan(app):
            cfg = _get_schedule_config()
            scheduler = Scheduler(
                interval_seconds=cfg["interval_seconds"],
                enabled=cfg["enabled"],
                pipeline_kwargs={
                    "signal_limit": cfg["signal_limit"],
                    "min_score": cfg["min_score"],
                    "weight_profile": cfg["weight_profile"],
                    "ideation_mode": cfg["ideation_mode"],
                },
            )
            app.state.scheduler = scheduler
            set_scheduler_ref(scheduler)
            await scheduler.start()
            try:
                yield
            finally:
                await scheduler.stop()

    app = FastAPI(
        title="Max Idea Engine",
        description="Pull-based idea service — query ideas, pull specs, contribute signals via REST and MCP.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(router, prefix="/api/v1")
    app.mount("/mcp", mcp_app)

    return app
