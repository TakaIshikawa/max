"""Tests for HubSpot contacts import adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from max.imports.hubspot_contacts_adapter import (
    HubSpotContactAdapter,
    HubSpotContactsAdapter,
)


def _contact(number: int, *, email: str | None = None) -> dict:
    return {
        "id": f"contact-{number}",
        "archived": False,
        "createdAt": "2026-05-01T10:00:00Z",
        "updatedAt": "2026-05-02T10:00:00Z",
        "properties": {
            "firstname": "Ada",
            "lastname": f"Lovelace {number}",
            "email": email or f"ada{number}@example.com",
            "company": "Analytical Engines",
            "lifecyclestage": "customer",
            "hubspot_owner_id": "owner-1",
            "createdate": "2026-05-01T10:00:00Z",
            "hs_lastmodifieddate": "2026-05-02T10:00:00Z",
        },
    }


@pytest.mark.asyncio
async def test_hubspot_contacts_fetches_list_pages_and_maps_metadata() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"results": [_contact(1)], "paging": {"next": {"after": "cursor-2"}}},
            )
        return httpx.Response(200, json={"results": [_contact(2)]})

    adapter = HubSpotContactsAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={"per_page": 1, "archived": False, "after": "cursor-1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert HubSpotContactAdapter is HubSpotContactsAdapter
    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer hubspot-token"
    assert requests[0].url.path == "/crm/v3/objects/contacts"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["archived"] == "false"
    assert requests[0].url.params["after"] == "cursor-1"
    assert requests[1].url.params["after"] == "cursor-2"
    assert set(requests[0].url.params.get_list("properties")) >= {
        "firstname",
        "lastname",
        "email",
        "company",
        "lifecyclestage",
        "hubspot_owner_id",
        "createdate",
        "hs_lastmodifieddate",
    }

    signal = signals[0]
    assert signal.id == "hubspot-contact:contact-1"
    assert signal.source_adapter == "hubspot_contacts_import"
    assert signal.source_type.value == "market"
    assert signal.title == "Ada Lovelace 1"
    assert signal.content == "HubSpot contact Ada Lovelace 1; ada1@example.com; company Analytical Engines; lifecycle customer"
    assert signal.author == "owner-1"
    assert signal.published_at is not None
    assert signal.metadata["signal_role"] == "customer"
    assert signal.metadata["contact_id"] == "contact-1"
    assert signal.metadata["name"] == "Ada Lovelace 1"
    assert signal.metadata["email"] == "ada1@example.com"
    assert signal.metadata["lifecycle_stage"] == "customer"
    assert signal.metadata["company"] == "Analytical Engines"
    assert signal.metadata["owner_id"] == "owner-1"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-02T10:00:00Z"
    assert signal.metadata["archived"] is False
    assert signal.metadata["properties"]["email"] == "ada1@example.com"
    assert signal.metadata["raw"]["id"] == "contact-1"
    assert "contact" in signal.tags


@pytest.mark.asyncio
async def test_hubspot_contacts_searches_when_updated_after_is_configured() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"results": [_contact(1)], "paging": {"next": {"after": "cursor-2"}}},
            )
        return httpx.Response(200, json={"results": [_contact(2, email="second@example.com")]})

    adapter = HubSpotContactsAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={
            "limit": 1,
            "updated_after": "2026-05-02T00:00:00Z",
            "after": "cursor-1",
            "archived": "true",
            "properties": ["email", "firstname", "lastname", "company", "lifecyclestage"],
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.method for request in requests] == ["POST", "POST"]
    assert requests[0].url.path == "/crm/v3/objects/contacts/search"
    first_payload = json.loads(requests[0].read())
    second_payload = json.loads(requests[1].read())
    assert first_payload["limit"] == 1
    assert first_payload["after"] == "cursor-1"
    assert first_payload["archived"] is True
    assert first_payload["properties"] == ["email", "firstname", "lastname", "company", "lifecyclestage"]
    assert {
        "propertyName": "hs_lastmodifieddate",
        "operator": "GTE",
        "value": "2026-05-02T00:00:00Z",
    } in first_payload["filterGroups"][0]["filters"]
    assert second_payload["after"] == "cursor-2"
    assert [signal.metadata["contact_id"] for signal in signals] == ["contact-1", "contact-2"]


@pytest.mark.asyncio
async def test_hubspot_contacts_uses_configured_properties_and_env_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUBSPOT_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_contact(1)]})

    adapter = HubSpotContactsAdapter(
        api_url="https://hubspot.example",
        config={"properties": "email,company,hubspot_owner_id", "archived": "false"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert requests[0].url.params.get_list("properties") == ["email", "company", "hubspot_owner_id"]
    assert requests[0].url.params["archived"] == "false"
    assert signals[0].metadata["email"] == "ada1@example.com"


@pytest.mark.asyncio
async def test_hubspot_contacts_empty_without_credentials_or_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotContactsAdapter().fetch() == []
    assert await HubSpotContactsAdapter(token="token").fetch(limit=0) == []


@pytest.mark.asyncio
async def test_hubspot_contacts_api_or_non_json_failure_returns_empty() -> None:
    failing = HubSpotContactsAdapter(
        token="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = HubSpotContactsAdapter(
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=2) == []
