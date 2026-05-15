"""Tests for HubSpot forms import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_forms_adapter import HubSpotFormsAdapter


FORM = {
    "id": "form-1",
    "name": "Demo request",
    "formType": "hubspot",
    "archived": False,
    "published": True,
    "fieldGroups": [{"fields": [{"label": "Email"}, {"label": "Company", "dependentFields": [{"label": "Company size"}]}]}],
    "submitActions": [{"type": "REDIRECT", "url": "https://example.com/thanks"}],
    "createdAt": "2026-05-01T10:00:00Z",
    "updatedAt": "2026-05-02T11:00:00Z",
    "portalId": 12345,
}


@pytest.mark.asyncio
async def test_hubspot_forms_fetches_multiple_forms_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [FORM, {**FORM, "id": "form-2", "name": "Contact us"}]})

    adapter = HubSpotFormsAdapter(
        token="hs-token",
        api_url="https://api.hubapi.test",
        config={"page_size": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requests[0].url.path == "/marketing/v3/forms"
    assert requests[0].url.params["limit"] == "2"
    assert requests[0].url.params["archived"] == "false"
    assert requests[0].headers["Authorization"] == "Bearer hs-token"
    assert [signal.metadata["form_id"] for signal in signals] == ["form-1", "form-2"]

    signal = signals[0]
    assert signal.id == "hubspot-form:form-1"
    assert signal.source_adapter == "hubspot_forms_import"
    assert signal.title == "Demo request"
    assert "fields Email, Company, Company size" in signal.content
    assert "submit actions REDIRECT: https://example.com/thanks" in signal.content
    assert signal.metadata["form_type"] == "hubspot"
    assert signal.metadata["archived"] is False
    assert signal.metadata["published"] is True
    assert signal.metadata["field_labels"] == ["Email", "Company", "Company size"]
    assert signal.metadata["submit_actions"] == ["REDIRECT: https://example.com/thanks"]
    assert signal.metadata["portal_id"] == 12345
    assert signal.metadata["raw"] == FORM


@pytest.mark.asyncio
async def test_hubspot_forms_handles_archived_forms_and_pagination() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"results": [{**FORM, "id": "archived", "archived": True}], "paging": {"next": {"after": "abc"}}})
        return httpx.Response(200, json={"results": [{**FORM, "id": "next"}]})

    adapter = HubSpotFormsAdapter(
        private_app_token="hs-token",
        config={"api_url": "https://api.hubapi.test", "archived": True, "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert requests[0].url.params["archived"] == "true"
    assert requests[1].url.params["after"] == "abc"
    assert [signal.metadata["form_id"] for signal in signals] == ["archived", "next"]
    assert signals[0].metadata["archived"] is True


@pytest.mark.asyncio
async def test_hubspot_forms_empty_without_token_or_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_PRIVATE_APP_TOKEN", raising=False)

    assert await HubSpotFormsAdapter().fetch() == []
    assert await HubSpotFormsAdapter(token="token").fetch(limit=0) == []

    empty = HubSpotFormsAdapter(
        token="token",
        api_url="https://api.hubapi.test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"results": []}))),
    )
    assert await empty.fetch(limit=5) == []
