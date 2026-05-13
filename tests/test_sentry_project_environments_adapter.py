"""Tests for Sentry project environments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_project_environments_adapter import SentryProjectEnvironmentsAdapter
from max.types.signal import SignalSourceType


def _environment(name: str, *, env_id: str | None = None, visibility: str = "visible") -> dict:
    return {
        "id": env_id or name,
        "name": name,
        "displayName": name.title(),
        "visibility": visibility,
        "dateCreated": "2026-05-01T10:00:00Z",
        "lastSeen": "2026-05-02T11:00:00Z",
    }


@pytest.mark.asyncio
async def test_sentry_project_environments_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[_environment("production", env_id="env-1")],
                headers={"Link": '<https://sentry.example/api/0/projects/acme/web/environments/?cursor=next>; rel="next"; results="true"'},
            )
        return httpx.Response(
            200,
            json=[_environment("staging", env_id="env-2", visibility="hidden")],
            headers={"Link": '<https://sentry.example/api/0/projects/acme/web/environments/?cursor=end>; rel="next"; results="false"'},
        )

    adapter = SentryProjectEnvironmentsAdapter(
        auth_token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={
            "organization_slug": "acme",
            "project_slugs": ["web"],
            "page_size": 1,
            "visibility": "visible",
            "name": "prod",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/projects/acme/web/environments/"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["visibility"] == "visible"
    assert requests[0].url.params["name"] == "prod"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert requests[1].url.params["cursor"] == "next"
    assert [signal.metadata["name"] for signal in signals] == ["production", "staging"]
    signal = signals[0]
    assert signal.id == "sentry-environment:acme:web:env-1"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "sentry_project_environments_import"
    assert signal.title == "web environment production"
    assert signal.metadata["sentry_organization_slug"] == "acme"
    assert signal.metadata["sentry_project_slug"] == "web"
    assert signal.metadata["sentry_environment_id"] == "env-1"
    assert signal.metadata["display_name"] == "Production"
    assert signal.metadata["visibility"] == "visible"
    assert signal.metadata["date_created"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["last_seen"] == "2026-05-02T11:00:00Z"
    assert signal.metadata["raw"]["id"] == "env-1"
    assert "environment" in signal.tags


@pytest.mark.asyncio
async def test_sentry_project_environments_respects_per_project_limit_and_aliases() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        project = request.url.path.split("/projects/acme/", 1)[1].split("/", 1)[0]
        return httpx.Response(200, json=[_environment(f"{project}-prod"), _environment(f"{project}-stage")])

    adapter = SentryProjectEnvironmentsAdapter(
        token="sentry-token",
        config={"org": "acme", "projects": [{"slug": "web"}, {"id": "api"}], "page_size": 10, "per_project_limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.params["per_page"] == "1"
    assert [signal.metadata["sentry_project_slug"] for signal in signals] == ["web", "api"]
    assert [signal.metadata["name"] for signal in signals] == ["web-prod", "api-prod"]


@pytest.mark.asyncio
async def test_sentry_project_environments_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    assert await SentryProjectEnvironmentsAdapter(config={"org": "acme", "projects": ["web"]}).fetch() == []
    assert await SentryProjectEnvironmentsAdapter(auth_token="token", config={"projects": ["web"]}).fetch() == []
    assert await SentryProjectEnvironmentsAdapter(auth_token="token", config={"org": "acme"}).fetch() == []
    assert await SentryProjectEnvironmentsAdapter(auth_token="token", config={"org": "acme", "projects": ["web"]}).fetch(limit=0) == []
