"""Minimal local shim for the optional `fastmcp` dependency.

The real package provides the MCP server implementation. The test suite in
this workspace only needs the registration surface so the REST app can import
and the MCP tool registration tests can monkeypatch the class.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI


class FastMCP:
    """Small compatibility stub used when the external dependency is unavailable."""

    def __init__(self, name: str, *args, **kwargs) -> None:
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.tools: list[str] = []
        self.resources: dict[str, str] = {}

    def tool(self, fn: Callable):
        self.tools.append(fn.__name__)
        return fn

    def resource(self, uri: str):
        def decorator(fn: Callable):
            self.resources[uri] = fn.__name__
            return fn

        return decorator

    def http_app(self, path: str = "/mcp") -> FastAPI:
        """Return a minimal ASGI app compatible with the real package's API."""
        return FastAPI(title=self.name)
