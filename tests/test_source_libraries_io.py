from __future__ import annotations

import httpx
import pytest

from max.sources.libraries_io import LibrariesIoAdapter


@pytest.mark.asyncio
async def test_fetch_normalizes_and_deduplicates_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {"name": "agent-kit", "description": "Agent framework", "platform": "NPM", "language": "TypeScript", "rank": 10, "stars": 500, "repository_url": "https://github.com/acme/agent-kit"},
                {"name": "agent-kit", "description": "Duplicate", "platform": "NPM", "repository_url": "https://github.com/acme/agent-kit"},
            ],
        )

    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: async_client(transport=httpx.MockTransport(handler)))
    adapter = LibrariesIoAdapter({"queries": ["agent"], "platforms": ["NPM"], "api_key": "key", "max_items": 5})

    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].source_adapter == "libraries_io"
    assert signals[0].title == "agent-kit"
    assert signals[0].metadata["platform"] == "NPM"
    assert "api_key=key" in str(requests[0].url)
    assert "platforms=NPM" in str(requests[0].url)


@pytest.mark.asyncio
async def test_fetch_uses_env_api_key_and_skips_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIBRARIES_IO_API_KEY", "env-key")
    async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="nope")

    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: async_client(transport=httpx.MockTransport(handler)))
    adapter = LibrariesIoAdapter({"queries": ["agent"], "max_items": 2})

    assert await adapter.fetch(limit=2) == []
