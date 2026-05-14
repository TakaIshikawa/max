"""Tests for Zendesk ticket side conversations import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.zendesk_ticket_side_conversations_adapter import ZendeskTicketSideConversationsImportAdapter


def _conversation(conversation_id: str = "sc_1") -> dict:
    return {
        "id": conversation_id,
        "subject": "Vendor escalation",
        "preview_text": "Can you confirm the rollout date?",
        "state": "open",
        "participants": [{"email": "vendor@example.com", "name": "Vendor"}],
        "created_by": {"email": "agent@example.com", "name": "Agent"},
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-01T11:00:00Z",
        "url": "https://max.zendesk.com/agent/tickets/42/side_conversations/sc_1",
    }


@pytest.mark.asyncio
async def test_zendesk_side_conversations_basic_auth_subdomain_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "max")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"side_conversations": [_conversation()], "next_page": None})

    adapter = ZendeskTicketSideConversationsImportAdapter(
        email="agent@example.com",
        token="api-token",
        config={"ticket_ids": [42], "per_page": 25},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=30)

    assert requests[0].url.path == "/api/v2/tickets/42/side_conversations.json"
    assert requests[0].url.params["per_page"] == "25"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert requests[0].headers["User-Agent"] == "max-zendesk-ticket-side-conversations-import/1"
    signal = signals[0]
    assert signal.id == "zendesk-ticket-side-conversation:42:sc_1"
    assert signal.source_adapter == "zendesk_ticket_side_conversations_import"
    assert signal.title == "Vendor escalation"
    assert signal.content == "Can you confirm the rollout date?"
    assert signal.author == "agent@example.com"
    assert signal.metadata["ticket_id"] == "42"
    assert signal.metadata["participants"][0]["email"] == "vendor@example.com"


@pytest.mark.asyncio
async def test_zendesk_side_conversations_oauth_next_page_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"side_conversations": [_conversation("sc_1")], "next_page": "https://max.zendesk.com/api/v2/page2.json"})
        return httpx.Response(200, json={"side_conversations": [_conversation("sc_2")], "next_page": None})

    adapter = ZendeskTicketSideConversationsImportAdapter(
        api_url="https://max.zendesk.com",
        oauth_token="oauth-token",
        config={"ticket_ids": [42, 43], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert requests[0].headers["Authorization"] == "Bearer oauth-token"
    assert [request.url.path for request in requests] == ["/api/v2/tickets/42/side_conversations.json", "/api/v2/page2.json"]
    assert [signal.metadata["side_conversation_id"] for signal in signals] == ["sc_1", "sc_2"]


@pytest.mark.asyncio
async def test_zendesk_side_conversations_empty_without_config_auth_or_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZENDESK_BASE_URL", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    monkeypatch.delenv("ZENDESK_EMAIL", raising=False)
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)
    monkeypatch.delenv("ZENDESK_OAUTH_TOKEN", raising=False)

    assert await ZendeskTicketSideConversationsImportAdapter(config={"ticket_ids": [42]}).fetch() == []
    assert await ZendeskTicketSideConversationsImportAdapter(api_url="https://max.zendesk.com", oauth_token="token").fetch() == []
    assert await ZendeskTicketSideConversationsImportAdapter(api_url="https://max.zendesk.com", oauth_token="token", config={"ticket_ids": [42]}).fetch(limit=0) == []

    failing = ZendeskTicketSideConversationsImportAdapter(
        api_url="https://max.zendesk.com",
        oauth_token="token",
        config={"ticket_ids": [42]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []
