"""Tests for Freshdesk ticket conversations import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.freshdesk_ticket_conversations_adapter import (
    FreshdeskTicketConversationsAdapter,
    FreshdeskTicketConversationsImportAdapter,
)


def _conversation(number: int, *, private: bool = False, body_text: str | None = None) -> dict:
    return {
        "id": 5000 + number,
        "user_id": 9000 + number,
        "from_email": f"agent{number}@example.com",
        "body": f"<p>HTML body {number}</p>",
        "body_text": body_text if body_text is not None else f"Plain body {number}",
        "incoming": not private,
        "private": private,
        "source": 0,
        "attachments": [{"id": "a"}],
        "created_at": f"2026-05-0{number}T10:00:00Z",
        "updated_at": f"2026-05-0{number}T11:00:00Z",
    }


@pytest.mark.asyncio
async def test_freshdesk_ticket_conversations_uses_config_auth_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_conversation(1)])

    adapter = FreshdeskTicketConversationsImportAdapter(
        config={
            "domain": "acme",
            "api_key": "freshdesk-key",
            "ticket_ids": ["42"],
            "updated_since": "2026-05-01T00:00:00Z",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert FreshdeskTicketConversationsAdapter is FreshdeskTicketConversationsImportAdapter
    assert adapter.domain == "acme.freshdesk.com"
    assert requests[0].url.path == "/api/v2/tickets/42/conversations"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].url.params["updated_since"] == "2026-05-01T00:00:00Z"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert len(signals) == 1
    assert signals[0].id == "freshdesk-ticket-conversation:42:5001"
    assert signals[0].source_adapter == "freshdesk_ticket_conversations_import"
    assert signals[0].source_type.value == "roadmap"
    assert signals[0].title == "Freshdesk ticket 42 reply"
    assert signals[0].content == "Plain body 1"
    assert signals[0].url == "https://acme.freshdesk.com/a/tickets/42"
    assert signals[0].author == "9001"
    assert signals[0].metadata["ticket_id"] == "42"
    assert signals[0].metadata["conversation_id"] == 5001
    assert signals[0].metadata["visibility"] == "public"
    assert signals[0].metadata["kind"] == "reply"
    assert signals[0].metadata["attachments_count"] == 1


@pytest.mark.asyncio
async def test_freshdesk_ticket_conversations_follows_link_header_and_total_limit() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(str(request.url))
        if len(paths) == 1:
            return httpx.Response(
                200,
                json=[_conversation(1)],
                headers={
                    "Link": '<https://acme.freshdesk.com/api/v2/tickets/42/conversations?page=2>; rel="next"',
                },
            )
        if "tickets/42" in str(request.url):
            return httpx.Response(200, json=[_conversation(2, private=True)])
        return httpx.Response(200, json=[_conversation(3)])

    adapter = FreshdeskTicketConversationsImportAdapter(
        domain="acme.freshdesk.com",
        api_key="freshdesk-key",
        config={"ticket_ids": ["42", "43"], "include_private_notes": True, "per_ticket_limit": 2, "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(paths) == 2
    assert [signal.metadata["conversation_id"] for signal in signals] == [5001, 5002]
    assert signals[1].metadata["visibility"] == "private"
    assert signals[1].metadata["kind"] == "note"


@pytest.mark.asyncio
async def test_freshdesk_ticket_conversations_page_params_private_filter_and_html_fallback() -> None:
    requested_pages: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_pages.append(request.url.params.get("page", ""))
        if request.url.params.get("page") == "1":
            return httpx.Response(200, json=[_conversation(1, private=True)])
        return httpx.Response(200, json=[_conversation(2, body_text="")])

    adapter = FreshdeskTicketConversationsImportAdapter(
        domain="acme",
        api_key="freshdesk-key",
        config={"ticket_id": 42, "per_ticket_limit": 2, "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requested_pages == ["1", "2"]
    assert len(signals) == 1
    assert signals[0].metadata["conversation_id"] == 5002
    assert signals[0].content == "<p>HTML body 2</p>"


@pytest.mark.asyncio
async def test_freshdesk_ticket_conversations_empty_without_config_env_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FRESHDESK_DOMAIN", raising=False)
    monkeypatch.delenv("FRESHDESK_API_KEY", raising=False)

    assert await FreshdeskTicketConversationsImportAdapter(config={"ticket_ids": ["42"]}).fetch() == []
    assert await FreshdeskTicketConversationsImportAdapter(domain="acme", api_key="key").fetch() == []
    assert (
        await FreshdeskTicketConversationsImportAdapter(
            domain="acme",
            api_key="key",
            config={"ticket_ids": ["42"]},
        ).fetch(limit=0)
        == []
    )

    failing = FreshdeskTicketConversationsImportAdapter(
        domain="acme",
        api_key="key",
        config={"ticket_ids": ["42"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )

    assert await failing.fetch(limit=2) == []
