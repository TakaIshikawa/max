"""Tests for HubSpot companies import adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from max.imports.hubspot_companies_adapter import (
    HubSpotCompaniesAdapter,
    HubSpotCompanyAdapter,
)


def _company(number: int, *, domain: str | None = None) -> dict:
    return {
        "id": f"company-{number}",
        "archived": False,
        "createdAt": "2026-05-01T10:00:00Z",
        "updatedAt": "2026-05-02T10:00:00Z",
        "properties": {
            "name": f"Analytical Engines {number}",
            "domain": domain or f"engine{number}.example.com",
            "industry": "Computer Software",
            "lifecyclestage": "customer",
            "type": "partner",
            "city": "London",
            "state": "London",
            "country": "GB",
            "hubspot_owner_id": "owner-1",
            "createdate": "2026-05-01T10:00:00Z",
            "hs_lastmodifieddate": "2026-05-02T10:00:00Z",
        },
    }


@pytest.mark.asyncio
async def test_hubspot_companies_fetches_list_pages_and_maps_metadata() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"results": [_company(1)], "paging": {"next": {"after": "cursor-2"}}},
            )
        return httpx.Response(200, json={"results": [_company(2)]})

    adapter = HubSpotCompaniesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={"per_page": 1, "archived": False, "after": "cursor-1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert HubSpotCompanyAdapter is HubSpotCompaniesAdapter
    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer hubspot-token"
    assert requests[0].url.path == "/crm/v3/objects/companies"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["archived"] == "false"
    assert requests[0].url.params["after"] == "cursor-1"
    assert requests[1].url.params["after"] == "cursor-2"
    assert set(requests[0].url.params.get_list("properties")) >= {
        "name",
        "domain",
        "industry",
        "lifecyclestage",
        "type",
        "hubspot_owner_id",
        "createdate",
        "hs_lastmodifieddate",
    }

    signal = signals[0]
    assert signal.id == "hubspot-company:company-1"
    assert signal.source_adapter == "hubspot_companies_import"
    assert signal.source_type.value == "market"
    assert signal.title == "Analytical Engines 1"
    assert signal.content == (
        "HubSpot company Analytical Engines 1; engine1.example.com; "
        "industry Computer Software; lifecycle customer; type partner"
    )
    assert signal.author == "owner-1"
    assert signal.published_at is not None
    assert signal.url == "https://app.hubspot.com/contacts/company/company-1"
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["company_id"] == "company-1"
    assert signal.metadata["hubspot_company_id"] == "company-1"
    assert signal.metadata["name"] == "Analytical Engines 1"
    assert signal.metadata["domain"] == "engine1.example.com"
    assert signal.metadata["industry"] == "Computer Software"
    assert signal.metadata["lifecycle_stage"] == "customer"
    assert signal.metadata["type"] == "partner"
    assert signal.metadata["city"] == "London"
    assert signal.metadata["country"] == "GB"
    assert signal.metadata["owner_id"] == "owner-1"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-02T10:00:00Z"
    assert signal.metadata["archived"] is False
    assert signal.metadata["properties"]["domain"] == "engine1.example.com"
    assert signal.metadata["raw"]["id"] == "company-1"
    assert "company" in signal.tags
    assert "hubspot" in signal.tags


@pytest.mark.asyncio
async def test_hubspot_companies_searches_when_updated_after_is_configured() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"results": [_company(1)], "paging": {"next": {"after": "cursor-2"}}},
            )
        return httpx.Response(200, json={"results": [_company(2, domain="second.example.com")]})

    adapter = HubSpotCompaniesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={
            "limit": 1,
            "updated_after": "2026-05-02T00:00:00Z",
            "after": "cursor-1",
            "archived": "true",
            "properties": ["name", "domain", "industry", "lifecyclestage"],
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.method for request in requests] == ["POST", "POST"]
    assert requests[0].url.path == "/crm/v3/objects/companies/search"
    first_payload = json.loads(requests[0].read())
    second_payload = json.loads(requests[1].read())
    assert first_payload["limit"] == 1
    assert first_payload["after"] == "cursor-1"
    assert first_payload["archived"] is True
    assert first_payload["properties"] == ["name", "domain", "industry", "lifecyclestage"]
    assert {
        "propertyName": "hs_lastmodifieddate",
        "operator": "GTE",
        "value": "2026-05-02T00:00:00Z",
    } in first_payload["filterGroups"][0]["filters"]
    assert second_payload["after"] == "cursor-2"
    assert [signal.metadata["company_id"] for signal in signals] == ["company-1", "company-2"]


@pytest.mark.asyncio
async def test_hubspot_companies_uses_configured_properties_and_env_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUBSPOT_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_company(1)]})

    adapter = HubSpotCompaniesAdapter(
        api_url="https://hubspot.example",
        config={"properties": "name,domain,industry", "archived": "false"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert requests[0].url.params.get_list("properties") == ["name", "domain", "industry"]
    assert requests[0].url.params["archived"] == "false"
    assert signals[0].metadata["domain"] == "engine1.example.com"


@pytest.mark.asyncio
async def test_hubspot_companies_empty_without_credentials_or_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotCompaniesAdapter().fetch() == []
    assert await HubSpotCompaniesAdapter(token="token").fetch(limit=0) == []


@pytest.mark.asyncio
async def test_hubspot_companies_api_or_non_json_failure_returns_empty() -> None:
    failing = HubSpotCompaniesAdapter(
        token="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = HubSpotCompaniesAdapter(
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=2) == []
