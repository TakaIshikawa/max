"""App factory — creates FastAPI app with MCP server mounted."""

from __future__ import annotations

from fastapi import FastAPI

from max.server.api import router
from max.server.mcp_tools import create_mcp_server


def create_app() -> FastAPI:
    """Create the combined FastAPI + MCP application."""
    mcp = create_mcp_server()
    mcp_app = mcp.http_app(path="/mcp")

    app = FastAPI(
        title="Max Idea Engine",
        description="Pull-based idea service — query ideas, pull specs, contribute signals via REST and MCP.",
        version="0.1.0",
        lifespan=mcp_app.router.lifespan_context,
    )

    app.include_router(router, prefix="/api/v1")
    app.mount("/mcp", mcp_app)

    return app
