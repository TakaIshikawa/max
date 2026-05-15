"""Tests for Zendesk organization memberships import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.zendesk_organization_memberships_adapter import (
    ZendeskOrganizationMembershipsAdapter,
    ZendeskOrganizationMembershipsImportAdapter,
)


MEMBERSHIP = {
    "id": 123,
    "user_id": 456,
    "organization_id": 789,
    "default": True,
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-02T11:00:00Z",
    "url": "https://acme.zendesk.com/api/v2/organization_memberships/123.json",
    "tags": ["enterprise", "admin"],
}


@pytest.mark.asyncio
async def test_zendesk_organization_memberships_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "organization_memberships": [MEMBERSHIP],
                    "next_page": "https://acme.zendesk.com/api/v2/organization_memberships.json?page=2",
                },
            )
        return httpx.Response(
            200,
            json={
                "organization_memberships": [{**MEMBERSHIP, "id": 124, "default": False}],
                "next_page": None,
            },
        )

    adapter = ZendeskOrganizationMembershipsAdapter(
        base_url="https://acme.zendesk.com",
        email="agent@example.com",
        token="zd-token",
        config={"page_size": 1, "user_id": 456, "organization_id": 789},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert ZendeskOrganizationMembershipsAdapter is ZendeskOrganizationMembershipsImportAdapter
    assert len(requests) == 2
    assert requests[0].url.path == "/api/v2/organization_memberships.json"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["user_id"] == "456"
    assert requests[0].url.params["organization_id"] == "789"
    assert requests[0].headers["User-Agent"] == "max-zendesk-organization-memberships-import/1"
    expected_auth = base64.b64encode(b"agent@example.com/token:zd-token").decode()
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[1].url.params["page"] == "2"

    assert [signal.metadata["membership_id"] for signal in signals] == [123, 124]
    signal = signals[0]
    assert signal.id == "zendesk-organization-membership:123"
    assert signal.source_adapter == "zendesk_organization_memberships_import"
    assert signal.source_type.value == "market"
    assert signal.title == "Zendesk organization membership 123"
    assert signal.content == "Zendesk organization membership; user 456; organization 789; default True"
    assert signal.url == MEMBERSHIP["url"]
    assert signal.author == "456"
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["user_id"] == 456
    assert signal.metadata["organization_id"] == 789
    assert signal.metadata["default"] is True
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-02T11:00:00Z"
    assert signal.metadata["tags"] == ["enterprise", "admin"]
    assert signal.metadata["raw"] == MEMBERSHIP
    assert "zendesk" in signal.tags
    assert "organization-membership" in signal.tags


@pytest.mark.asyncio
async def test_zendesk_organization_memberships_supports_bearer_next_page_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "organization_memberships": [
                    {**MEMBERSHIP, "id": 125},
                    {**MEMBERSHIP, "id": 126},
                ],
                "next_page": "https://acme.zendesk.com/api/v2/organization_memberships.json?page=3",
            },
        )

    adapter = ZendeskOrganizationMembershipsAdapter(
        base_url="https://acme.zendesk.com",
        access_token="access-token",
        config={"next_page": "https://acme.zendesk.com/api/v2/organization_memberships.json?page=2", "page_size": 50},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer access-token"
    assert requests[0].url.params["page"] == "2"
    assert "per_page" not in requests[0].url.params
    assert [signal.metadata["membership_id"] for signal in signals] == [125]


@pytest.mark.asyncio
async def test_zendesk_organization_memberships_empty_without_required_config_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZENDESK_BASE_URL", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    monkeypatch.delenv("ZENDESK_EMAIL", raising=False)
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)
    monkeypatch.delenv("ZENDESK_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ZENDESK_BEARER_TOKEN", raising=False)

    assert await ZendeskOrganizationMembershipsAdapter(token="token").fetch() == []
    assert await ZendeskOrganizationMembershipsAdapter(base_url="https://acme.zendesk.com").fetch() == []
    assert await ZendeskOrganizationMembershipsAdapter(base_url="https://acme.zendesk.com", token="token").fetch(limit=0) == []

    failing = ZendeskOrganizationMembershipsAdapter(
        base_url="https://acme.zendesk.com",
        email="agent@example.com",
        token="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
