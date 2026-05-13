"""Tests for Sentry organization members import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_organization_members_adapter import (
    SentryOrganizationMemberAdapter,
    SentryOrganizationMembersAdapter,
)


def _member(number: int, *, pending: bool = False) -> dict:
    return {
        "id": f"m{number}",
        "email": f"user{number}@example.test",
        "name": f"User {number}",
        "role": "member",
        "roleName": "Member",
        "pending": pending,
        "expired": False,
        "dateCreated": "2026-05-01T10:00:00Z",
        "teams": [{"id": "t1", "slug": "backend", "name": "Backend"}],
        "flags": {"sso:linked": True},
        "user": {"id": f"u{number}", "username": f"user{number}", "email": f"user{number}@example.test"},
    }


@pytest.mark.asyncio
async def test_sentry_organization_members_fetches_cursor_pages_and_maps_members() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[_member(1)],
                headers={
                    "Link": '<https://sentry.example/api/0/organizations/acme/members/?cursor=next>; rel="next"; results="true"; cursor="next"'
                },
            )
        return httpx.Response(
            200,
            json=[_member(2, pending=True)],
            headers={
                "Link": '<https://sentry.example/api/0/organizations/acme/members/?cursor=end>; rel="next"; results="false"; cursor="end"'
            },
        )

    adapter = SentryOrganizationMembersAdapter(
        auth_token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={"organization_slug": "acme", "per_page": 1, "query": "user", "team": "backend"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert SentryOrganizationMemberAdapter is SentryOrganizationMembersAdapter
    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/organizations/acme/members/"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["query"] == "user"
    assert requests[0].url.params["team"] == "backend"
    assert "cursor" not in requests[0].url.params
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert requests[1].url.params["cursor"] == "next"

    signal = signals[0]
    assert signal.id == "sentry-organization-member:acme:m1"
    assert signal.source_adapter == "sentry_organization_members_import"
    assert signal.source_type.value == "market"
    assert signal.title == "Sentry member User 1"
    assert signal.metadata["sentry_organization_slug"] == "acme"
    assert signal.metadata["member_id"] == "m1"
    assert signal.metadata["role"] == "member"
    assert signal.metadata["role_name"] == "Member"
    assert signal.metadata["email"] == "user1@example.test"
    assert signal.metadata["name"] == "User 1"
    assert signal.metadata["invite_status"] == "accepted"
    assert signal.metadata["teams"] == [{"id": "t1", "slug": "backend", "name": "Backend"}]
    assert signal.metadata["flags"]["sso:linked"] is True
    assert signal.metadata["raw"]["id"] == "m1"
    assert signals[1].metadata["invite_status"] == "pending"


@pytest.mark.asyncio
async def test_sentry_organization_members_uses_env_token_and_org_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_member(1)])

    adapter = SentryOrganizationMembersAdapter(
        config={"org": "acme"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert requests[0].url.path == "/api/0/organizations/acme/members/"


@pytest.mark.asyncio
async def test_sentry_organization_members_requires_auth_org_and_positive_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    assert await SentryOrganizationMembersAdapter(config={"organization_slug": "acme"}).fetch() == []
    assert await SentryOrganizationMembersAdapter(token="token").fetch() == []
    assert await SentryOrganizationMembersAdapter(token="token", config={"org": "acme"}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_sentry_organization_members_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = SentryOrganizationMembersAdapter(
        token="token",
        config={"organization_slug": "acme"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=10) == []
