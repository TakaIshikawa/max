"""Tests for Zendesk ticket forms import adapter."""

from __future__ import annotations

import httpx
import pytest
import base64

from max.imports.zendesk_ticket_forms_adapter import ZendeskTicketFormsAdapter


FORM = {
    "id": 123,
    "name": "Bug report",
    "display_name": "Report a bug",
    "active": True,
    "default": False,
    "end_user_visible": True,
    "ticket_field_ids": [11, 22],
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-02T11:00:00Z",
    "url": "https://acme.zendesk.com/api/v2/ticket_forms/123.json",
}


@pytest.mark.asyncio
async def test_zendesk_ticket_forms_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "ticket_forms": [FORM],
                    "next_page": "https://acme.zendesk.com/api/v2/ticket_forms.json?page=2",
                },
            )
        return httpx.Response(200, json={"ticket_forms": [{**FORM, "id": 124, "name": "Refund"}], "next_page": None})

    adapter = ZendeskTicketFormsAdapter(
        base_url="https://acme.zendesk.com",
        email="agent@example.com",
        token="zd-token",
        config={"page_size": 1, "active": True},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/v2/ticket_forms.json"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["active"] == "true"
    assert requests[0].headers["User-Agent"] == "max-zendesk-ticket-forms-import/1"
    expected_auth = base64.b64encode(b"agent@example.com/token:zd-token").decode()
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[1].url.params["page"] == "2"

    signal = signals[0]
    assert signal.id == "zendesk-ticket-form:123"
    assert signal.source_adapter == "zendesk_ticket_forms_import"
    assert signal.title == "Bug report"
    assert signal.content == "Zendesk ticket form; Bug report; Report a bug; active True; default False; end user visible True"
    assert signal.url == FORM["url"]
    assert signal.metadata["form_id"] == 123
    assert signal.metadata["name"] == "Bug report"
    assert signal.metadata["display_name"] == "Report a bug"
    assert signal.metadata["active"] is True
    assert signal.metadata["default"] is False
    assert signal.metadata["end_user_visible"] is True
    assert signal.metadata["ticket_field_ids"] == [11, 22]
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-02T11:00:00Z"
    assert signal.metadata["raw"] == FORM


@pytest.mark.asyncio
async def test_zendesk_ticket_forms_respects_active_filter_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ticket_forms": [FORM, {**FORM, "id": 124, "active": False}]})

    adapter = ZendeskTicketFormsAdapter(
        config={"subdomain": "acme", "email": "agent@example.com", "api_token": "zd-token", "active": False},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 1
    assert requests[0].url.host == "acme.zendesk.com"
    assert requests[0].url.params["active"] == "false"
    assert [signal.metadata["form_id"] for signal in signals] == [124]


@pytest.mark.asyncio
async def test_zendesk_ticket_forms_empty_without_required_config_or_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZENDESK_BASE_URL", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    monkeypatch.delenv("ZENDESK_EMAIL", raising=False)
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)

    assert await ZendeskTicketFormsAdapter(email="agent@example.com", token="token").fetch() == []
    assert await ZendeskTicketFormsAdapter(base_url="https://acme.zendesk.com", token="token").fetch() == []
    assert await ZendeskTicketFormsAdapter(base_url="https://acme.zendesk.com", email="agent@example.com").fetch() == []
    assert await ZendeskTicketFormsAdapter(base_url="https://acme.zendesk.com", email="agent@example.com", token="token").fetch(limit=0) == []

    failing = ZendeskTicketFormsAdapter(
        base_url="https://acme.zendesk.com",
        email="agent@example.com",
        token="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
