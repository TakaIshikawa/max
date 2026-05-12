"""Tests for Zendesk ticket audits import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.zendesk_ticket_audits_adapter import (
    ZendeskTicketAuditsAdapter,
    ZendeskTicketAuditsImportAdapter,
)


def _audit(audit_id: int = 8001, event_id: int = 9001) -> dict:
    return {
        "id": audit_id,
        "ticket_id": 42,
        "author_id": 1234,
        "created_at": "2026-05-01T10:00:00Z",
        "via": {"channel": "api"},
        "metadata": {"system": {"client": "curl"}},
        "events": [
            {
                "id": event_id,
                "type": "Change",
                "field_name": "status",
                "previous_value": "open",
                "value": "pending",
            }
        ],
    }


@pytest.mark.asyncio
async def test_zendesk_ticket_audits_basic_auth_fetches_flattens_and_maps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "acme")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"audits": [_audit()], "next_page": None})

    adapter = ZendeskTicketAuditsImportAdapter(
        email="agent@example.com",
        api_token="api-token",
        config={"ticket_ids": [42], "page_size": 25},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=30)

    assert ZendeskTicketAuditsAdapter is ZendeskTicketAuditsImportAdapter
    assert requests[0].url == "https://acme.zendesk.com/api/v2/tickets/42/audits.json?page%5Bsize%5D=25"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert requests[0].headers["User-Agent"] == "max-zendesk-ticket-audits-import/1"
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "zendesk-ticket-audit-event:42:8001:9001"
    assert signal.source_adapter == "zendesk_ticket_audits_import"
    assert signal.title == "Zendesk ticket 42 audit Change"
    assert signal.content == "Change changed status from open to pending"
    assert signal.url == "https://acme.zendesk.com/agent/tickets/42"
    assert signal.author == "1234"
    assert signal.metadata["ticket_id"] == "42"
    assert signal.metadata["audit_id"] == 8001
    assert signal.metadata["event_id"] == 9001
    assert signal.metadata["via"]["channel"] == "api"
    assert "ticket-audit" in signal.tags


@pytest.mark.asyncio
async def test_zendesk_ticket_audits_oauth_follows_next_page_and_honors_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "audits": [_audit(8001, 9001)],
                    "next_page": "https://max.zendesk.com/api/v2/tickets/42/audits/page2.json",
                },
            )
        return httpx.Response(200, json={"audits": [_audit(8002, 9002)], "next_page": None})

    adapter = ZendeskTicketAuditsImportAdapter(
        base_url="https://max.zendesk.com",
        oauth_token="oauth-token",
        config={"ticket_ids": [42, 43], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert requests[0].headers["Authorization"] == "Bearer oauth-token"
    assert [request.url.path for request in requests] == [
        "/api/v2/tickets/42/audits.json",
        "/api/v2/tickets/42/audits/page2.json",
    ]
    assert [signal.metadata["audit_id"] for signal in signals] == [8001, 8002]


@pytest.mark.asyncio
async def test_zendesk_ticket_audits_empty_without_config_auth_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZENDESK_BASE_URL", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    monkeypatch.delenv("ZENDESK_EMAIL", raising=False)
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)
    monkeypatch.delenv("ZENDESK_OAUTH_TOKEN", raising=False)

    assert await ZendeskTicketAuditsImportAdapter(config={"ticket_ids": [42]}).fetch() == []
    assert await ZendeskTicketAuditsImportAdapter(base_url="https://max.zendesk.com", oauth_token="token").fetch() == []
    assert await ZendeskTicketAuditsImportAdapter(base_url="https://max.zendesk.com", oauth_token="token", config={"ticket_ids": [42]}).fetch(limit=0) == []

    failing = ZendeskTicketAuditsImportAdapter(
        base_url="https://max.zendesk.com",
        oauth_token="token",
        config={"ticket_ids": [42]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []
