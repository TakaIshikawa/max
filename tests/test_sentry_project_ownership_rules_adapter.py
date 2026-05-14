"""Tests for Sentry project ownership rules import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_project_ownership_rules_adapter import SentryProjectOwnershipRulesAdapter
from max.types.signal import SignalSourceType


OWNERSHIP = {
    "raw": "# Owners\npath:src/api/** @acme/backend @alice\nmodule:billing @acme/billing",
    "fallthrough": True,
    "dateUpdated": "2026-05-01T10:00:00Z",
    "url": "https://sentry.example/settings/acme/projects/web/ownership/",
}


@pytest.mark.asyncio
async def test_sentry_project_ownership_rules_fetches_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=OWNERSHIP)

    adapter = SentryProjectOwnershipRulesAdapter(
        auth_token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={"organization_slug": "acme", "project_slugs": ["web"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 1
    assert requests[0].url.path == "/api/0/projects/acme/web/ownership/"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[0].headers["User-Agent"] == "max-sentry-project-ownership-rules-import/1"

    signal = signals[0]
    assert signal.id == "sentry-ownership-rules:acme:web"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "sentry_project_ownership_rules_import"
    assert signal.title == "web Sentry ownership rules"
    assert signal.content == "Sentry ownership rules for web; 2 parsed rules; fallthrough True"
    assert signal.url == OWNERSHIP["url"]
    assert signal.metadata["sentry_organization_slug"] == "acme"
    assert signal.metadata["sentry_project_slug"] == "web"
    assert signal.metadata["raw_ownership"] == OWNERSHIP["raw"]
    assert signal.metadata["fallthrough"] is True
    assert signal.metadata["date_updated"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["rule_rows"] == [
        {
            "line_number": 2,
            "raw": "path:src/api/** @acme/backend @alice",
            "matchers": ["path:src/api/**"],
            "owners": ["@acme/backend", "@alice"],
        },
        {
            "line_number": 3,
            "raw": "module:billing @acme/billing",
            "matchers": ["module:billing"],
            "owners": ["@acme/billing"],
        },
    ]
    assert signal.metadata["raw"] == OWNERSHIP


@pytest.mark.asyncio
async def test_sentry_project_ownership_rules_respects_multiple_projects_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        project = request.url.path.split("/projects/acme/", 1)[1].split("/", 1)[0]
        return httpx.Response(
            200,
            json={
                "rawOwnership": f"path:src/{project}/** @acme/{project}",
                "fallThrough": False,
                "date_updated": "2026-05-02T11:00:00Z",
            },
        )

    adapter = SentryProjectOwnershipRulesAdapter(
        token="sentry-token",
        config={"org": "acme", "projects": ["web", "api", "worker"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/projects/acme/web/ownership/"
    assert requests[1].url.path == "/api/0/projects/acme/api/ownership/"
    assert [signal.metadata["sentry_project_slug"] for signal in signals] == ["web", "api"]
    assert signals[0].metadata["raw_ownership"] == "path:src/web/** @acme/web"
    assert signals[0].metadata["fallthrough"] is False


@pytest.mark.asyncio
async def test_sentry_project_ownership_rules_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    assert await SentryProjectOwnershipRulesAdapter(config={"org": "acme", "projects": ["web"]}).fetch() == []
    assert await SentryProjectOwnershipRulesAdapter(auth_token="token", config={"projects": ["web"]}).fetch() == []
    assert await SentryProjectOwnershipRulesAdapter(auth_token="token", config={"org": "acme"}).fetch() == []
    assert await SentryProjectOwnershipRulesAdapter(auth_token="token", config={"org": "acme", "projects": ["web"]}).fetch(limit=0) == []

    failing = SentryProjectOwnershipRulesAdapter(
        auth_token="bad",
        config={"org": "acme", "projects": ["web"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
