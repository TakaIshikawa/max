"""Tests for HubSpot owners import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_owners_adapter import HubSpotOwnerAdapter, HubSpotOwnersAdapter
from max.types.signal import SignalSourceType


def _owner(
    number: int,
    *,
    email: str | None = None,
    archived: bool = False,
    teams: list[dict] | None = None,
) -> dict:
    return {
        "id": f"owner-{number}",
        "userId": number * 10,
        "email": email or f"owner{number}@example.com",
        "firstName": f"Owner{number}",
        "lastName": "Person",
        "createdAt": f"2026-05-{number:02d}T09:00:00Z",
        "updatedAt": f"2026-05-{number + 1:02d}T09:00:00Z",
        "archivedAt": f"2026-05-{number + 2:02d}T09:00:00Z" if archived else None,
        "archived": archived,
        "teams": teams
        if teams is not None
        else [{"id": "team-1", "name": "Sales", "primary": True}],
    }


@pytest.mark.asyncio
async def test_hubspot_owners_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"results": [_owner(1)], "paging": {"next": {"after": "cursor-2"}}},
            )
        return httpx.Response(200, json={"results": [_owner(2, archived=True)]})

    adapter = HubSpotOwnersAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={"page_size": 1, "archived": True},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert HubSpotOwnerAdapter is HubSpotOwnersAdapter
    assert len(requests) == 2
    assert requests[0].url.path == "/crm/v3/owners"
    assert requests[0].headers["Authorization"] == "Bearer hubspot-token"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["archived"] == "true"
    assert "after" not in requests[0].url.params
    assert requests[1].url.params["after"] == "cursor-2"
    assert [signal.metadata["owner_id"] for signal in signals] == ["owner-1", "owner-2"]

    signal = signals[0]
    assert signal.id == "hubspot-owner:owner-1"
    assert signal.source_type == SignalSourceType.MARKET
    assert signal.source_adapter == "hubspot_owners_import"
    assert signal.title == "HubSpot owner Owner1 Person"
    assert signal.content == "HubSpot owner; Owner1 Person; owner1@example.com; user 10; teams Sales"
    assert signal.author == "owner1@example.com"
    assert signal.published_at is not None
    assert signal.metadata["hubspot_owner_id"] == "owner-1"
    assert signal.metadata["user_id"] == "10"
    assert signal.metadata["email"] == "owner1@example.com"
    assert signal.metadata["first_name"] == "Owner1"
    assert signal.metadata["last_name"] == "Person"
    assert signal.metadata["name"] == "Owner1 Person"
    assert signal.metadata["teams"][0]["id"] == "team-1"
    assert signal.metadata["team_summaries"] == ["Sales"]
    assert signal.metadata["archived"] is False
    assert signal.metadata["created_at"] == "2026-05-01T09:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-02T09:00:00Z"
    assert signal.metadata["raw"]["id"] == "owner-1"
    assert signal.url == "https://app.hubspot.com/settings/users/owner-1"
    assert "hubspot" in signal.tags
    assert "owner" in signal.tags
    assert "active" in signal.tags
    assert "archived" in signals[1].tags
    assert signals[1].metadata["archived_at"] == "2026-05-04T09:00:00Z"


@pytest.mark.asyncio
async def test_hubspot_owners_filters_email_client_side_and_continues_paging() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "results": [_owner(1, email="other@example.com")],
                    "paging": {"next": {"after": "cursor-2"}},
                },
            )
        return httpx.Response(200, json={"results": [_owner(2, email="Target@Example.com")]})

    adapter = HubSpotOwnersAdapter(
        access_token="access-token",
        config={"email": "target@example.com", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 2
    assert requests[0].url.params["archived"] == "false"
    assert requests[1].url.params["after"] == "cursor-2"
    assert [signal.metadata["email"] for signal in signals] == ["Target@Example.com"]


@pytest.mark.asyncio
async def test_hubspot_owners_reads_config_token_api_url_and_archived_parameter() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_owner(1)]})

    adapter = HubSpotOwnersAdapter(
        config={
            "private_app_token": "private-token",
            "api_url": "https://hubspot.local/",
            "archived": "yes",
            "page_size": 50,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert requests[0].url.scheme == "https"
    assert requests[0].url.host == "hubspot.local"
    assert requests[0].headers["Authorization"] == "Bearer private-token"
    assert requests[0].url.params["limit"] == "3"
    assert requests[0].url.params["archived"] == "true"
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_hubspot_owners_respects_requested_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_owner(1), _owner(2), _owner(3)]})

    adapter = HubSpotOwnersAdapter(
        private_app_token="private-token",
        config={"page_size": 500},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert requests[0].url.params["limit"] == "2"
    assert [signal.metadata["owner_id"] for signal in signals] == ["owner-1", "owner-2"]


@pytest.mark.asyncio
async def test_hubspot_owners_empty_without_token_non_positive_limit_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_PRIVATE_APP_TOKEN", raising=False)

    assert await HubSpotOwnersAdapter().fetch() == []
    assert await HubSpotOwnersAdapter(token="token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = HubSpotOwnersAdapter(
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=2) == []
