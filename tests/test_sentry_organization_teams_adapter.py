"""Tests for Sentry organization teams import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_organization_teams_adapter import (
    SentryOrganizationTeamAdapter,
    SentryOrganizationTeamsAdapter,
)


def _team(number: int, *, slug: str | None = None) -> dict:
    return {
        "id": f"t{number}",
        "slug": slug or f"backend-{number}",
        "name": f"Backend {number}",
        "memberCount": number + 2,
        "projectCount": number + 4,
        "dateCreated": "2026-05-01T10:00:00Z",
        "isMember": True,
        "teamRole": "admin",
    }


@pytest.mark.asyncio
async def test_sentry_organization_teams_fetches_cursor_pages_and_maps_teams() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[_team(1, slug="backend")],
                headers={
                    "Link": '<https://sentry.example/api/0/organizations/acme/teams/?cursor=next>; rel="next"; results="true"; cursor="next"'
                },
            )
        return httpx.Response(
            200,
            json=[_team(2, slug="frontend")],
            headers={
                "Link": '<https://sentry.example/api/0/organizations/acme/teams/?cursor=end>; rel="next"; results="false"; cursor="end"'
            },
        )

    adapter = SentryOrganizationTeamsAdapter(
        auth_token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={"organization_slug": "acme", "per_page": 1, "query": "back"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert SentryOrganizationTeamAdapter is SentryOrganizationTeamsAdapter
    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/organizations/acme/teams/"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["query"] == "back"
    assert "cursor" not in requests[0].url.params
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert requests[1].url.params["cursor"] == "next"

    signal = signals[0]
    assert signal.id == "sentry-organization-team:acme:backend"
    assert signal.source_adapter == "sentry_organization_teams_import"
    assert signal.source_type.value == "failure_data"
    assert signal.title == "Sentry team Backend 1"
    assert signal.content == "Sentry organization team Backend 1; slug backend; 3 members; 5 projects"
    assert signal.url == "https://sentry.io/organizations/acme/teams/backend/"
    assert signal.published_at is not None
    assert signal.metadata["signal_role"] == "failure_data"
    assert signal.metadata["sentry_organization_slug"] == "acme"
    assert signal.metadata["team_id"] == "t1"
    assert signal.metadata["sentry_team_id"] == "t1"
    assert signal.metadata["slug"] == "backend"
    assert signal.metadata["name"] == "Backend 1"
    assert signal.metadata["member_count"] == 3
    assert signal.metadata["project_count"] == 5
    assert signal.metadata["date_created"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["is_member"] is True
    assert signal.metadata["team_role"] == "admin"
    assert signal.metadata["raw"]["id"] == "t1"
    assert "sentry" in signal.tags
    assert "team" in signal.tags
    assert signals[1].metadata["slug"] == "frontend"


@pytest.mark.asyncio
async def test_sentry_organization_teams_uses_env_token_and_org_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTRY_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_team(1)])

    adapter = SentryOrganizationTeamsAdapter(
        config={"org_slug": "acme"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert requests[0].url.path == "/api/0/organizations/acme/teams/"

    organization_adapter = SentryOrganizationTeamsAdapter(
        token="token",
        config={"organization": "other"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await organization_adapter.fetch(limit=1)
    assert requests[1].url.path == "/api/0/organizations/other/teams/"


@pytest.mark.asyncio
async def test_sentry_organization_teams_respects_page_size_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_team(1)])

    adapter = SentryOrganizationTeamsAdapter(
        token="token",
        config={"organization_slug": "acme", "page_size": 500},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await adapter.fetch(limit=200)

    assert requests[0].url.params["per_page"] == "100"


@pytest.mark.asyncio
async def test_sentry_organization_teams_requires_auth_org_and_positive_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("SENTRY_TOKEN", raising=False)

    assert await SentryOrganizationTeamsAdapter(config={"organization_slug": "acme"}).fetch() == []
    assert await SentryOrganizationTeamsAdapter(token="token").fetch() == []
    assert await SentryOrganizationTeamsAdapter(token="token", config={"organization_slug": "acme"}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_sentry_organization_teams_http_or_non_json_error_returns_empty() -> None:
    failing = SentryOrganizationTeamsAdapter(
        token="token",
        config={"organization_slug": "acme"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=10) == []

    non_json = SentryOrganizationTeamsAdapter(
        token="token",
        config={"organization_slug": "acme"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=10) == []
