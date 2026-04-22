"""App factory — creates FastAPI app with MCP server and scheduler."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from max import config
from max.server.api import router
from max.server.mcp_tools import create_mcp_server, set_scheduler_ref
from max.server.rate_limit import RateLimitMiddleware
from max.server.scheduler import Scheduler

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() == "true"


def _get_schedule_config() -> dict:
    """Read schedule config fresh from env (supports CLI overrides)."""
    return {
        "interval_seconds": int(os.getenv("MAX_SCHEDULE_INTERVAL", "21600")),
        "enabled": _env_bool("MAX_SCHEDULE_ENABLED", True),
        "profile": os.getenv("MAX_SCHEDULE_PIPELINE_PROFILE"),
        "include_all": _env_bool("MAX_SCHEDULE_INCLUDE_ALL", False),
        "signal_limit": int(os.getenv("MAX_SCHEDULE_SIGNAL_LIMIT", "30")),
        "min_score": float(os.getenv("MAX_SCHEDULE_MIN_SCORE", "50.0")),
        "weight_profile": os.getenv("MAX_SCHEDULE_PROFILE", "default"),
        "ideation_mode": os.getenv("MAX_SCHEDULE_MODE", "direct"),
        "quality_loop_enabled": _env_bool("MAX_SCHEDULE_QUALITY_LOOP_ENABLED", False),
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
                profile=cfg["profile"],
                include_all=cfg["include_all"],
                pipeline_kwargs={
                    "signal_limit": cfg["signal_limit"],
                    "min_score": cfg["min_score"],
                    "weight_profile": cfg["weight_profile"],
                    "ideation_mode": cfg["ideation_mode"],
                    "quality_loop_enabled": cfg["quality_loop_enabled"],
                },
            )
            app.state.started_at = time.monotonic()
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

    # Add rate limiting middleware if enabled
    if config.MAX_RATE_LIMIT_ENABLED:
        app.add_middleware(
            RateLimitMiddleware,
            rpm=config.MAX_RATE_LIMIT_RPM,
            excluded_paths={"/api/v1/health", "/mcp"},
        )

    # Add security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.method != "GET":
            response.headers["Cache-Control"] = "no-store"
        return response

    # Add CORS middleware if origins are configured
    if config.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.CORS_ORIGINS,
            allow_credentials=config.MAX_CORS_ALLOW_CREDENTIALS,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["*"],
        )

    app.include_router(router, prefix="/api/v1")
    app.mount("/mcp", mcp_app)

    return app
