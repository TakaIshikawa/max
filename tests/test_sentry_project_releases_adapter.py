"""Tests for Sentry project releases import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_project_releases_adapter import SentryProjectReleasesAdapter
from max.types.signal import SignalSourceType


def _release(version: str) -> dict:
    return {
        "id": f"r-{version}",
        "version": version,
        "shortVersion": version.split("+", 1)[0],
        "status": "open",
        "dateCreated": "2026-05-01T10:00:00Z",
        "dateReleased": "2026-05-02T11:00:00Z",
        "commitCount": 3,
        "lastCommit": {"id": "abc123", "message": "Ship release"},
        "owner": {"id": "u1", "name": "Ada Lovelace", "email": "ada@example.com"},
        "url": f"https://sentry.example/releases/{version}",
    }


@pytest.mark.asyncio
async def test_sentry_project_releases_fetches_pages_and_maps_release_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[_release("1.0.0")],
                headers={"Link": '<https://sentry.example/api/0/projects/acme/web/releases/?cursor=next>; rel="next"; results="true"'},
            )
        return httpx.Response(
            200,
            json=[_release("1.0.1")],
            headers={"Link": '<https://sentry.example/api/0/projects/acme/web/releases/?cursor=end>; rel="next"; results="false"'},
        )

    adapter = SentryProjectReleasesAdapter(
        auth_token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={
            "organization_slug": "acme",
            "project_slugs": ["web"],
            "page_size": 1,
            "query": "version:1",
            "status": "open",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/projects/acme/web/releases/"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["query"] == "version:1"
    assert requests[0].url.params["status"] == "open"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert requests[1].url.params["cursor"] == "next"
    assert [signal.metadata["version"] for signal in signals] == ["1.0.0", "1.0.1"]
    signal = signals[0]
    assert signal.id == "sentry-release:web:1.0.0"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "sentry_project_releases_import"
    assert signal.title == "web release 1.0.0"
    assert signal.url == "https://sentry.example/releases/1.0.0"
    assert signal.author == "Ada Lovelace"
    assert signal.metadata["sentry_project_slug"] == "web"
    assert signal.metadata["short_version"] == "1.0.0"
    assert signal.metadata["date_created"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["date_released"] == "2026-05-02T11:00:00Z"
    assert signal.metadata["commit_count"] == 3
    assert signal.metadata["last_commit"]["id"] == "abc123"
    assert signal.metadata["owner"]["email"] == "ada@example.com"
    assert signal.metadata["raw"]["id"] == "r-1.0.0"


@pytest.mark.asyncio
async def test_sentry_project_releases_respects_per_project_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        project = request.url.path.split("/projects/acme/", 1)[1].split("/", 1)[0]
        return httpx.Response(200, json=[_release(f"{project}-1"), _release(f"{project}-2")])

    adapter = SentryProjectReleasesAdapter(
        token="sentry-token",
        config={"org": "acme", "projects": ["web", "api"], "page_size": 10, "per_project_limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.params["per_page"] == "1"
    assert [signal.metadata["sentry_project_slug"] for signal in signals] == ["web", "api"]
    assert [signal.metadata["version"] for signal in signals] == ["web-1", "api-1"]


@pytest.mark.asyncio
async def test_sentry_project_releases_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    assert await SentryProjectReleasesAdapter(config={"org": "acme", "projects": ["web"]}).fetch() == []
    assert await SentryProjectReleasesAdapter(auth_token="token", config={"projects": ["web"]}).fetch() == []
    assert await SentryProjectReleasesAdapter(auth_token="token", config={"org": "acme"}).fetch() == []
    assert await SentryProjectReleasesAdapter(auth_token="token", config={"org": "acme", "projects": ["web"]}).fetch(limit=0) == []
