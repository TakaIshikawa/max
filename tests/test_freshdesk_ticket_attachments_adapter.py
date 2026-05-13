"""Tests for Freshdesk ticket attachments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.freshdesk_ticket_attachments_adapter import (
    FreshdeskTicketAttachmentsAdapter,
    FreshdeskTicketAttachmentsImportAdapter,
)


def _conversation(number: int, *, private: bool = False, attachments: list[dict] | None = None) -> dict:
    return {
        "id": 5000 + number,
        "user_id": 9000 + number,
        "from_email": f"agent{number}@example.com",
        "body": f"<p>HTML body {number}</p>",
        "body_text": f"Plain body {number}",
        "incoming": not private,
        "private": private,
        "source": 0,
        "attachments": attachments
        if attachments is not None
        else [
            {
                "id": 7000 + number,
                "name": f"debug-{number}.txt",
                "content_type": "text/plain",
                "size": 128 + number,
                "attachment_url": f"https://acme.freshdesk.com/helpdesk/attachments/{7000 + number}",
            }
        ],
        "created_at": f"2026-05-0{number}T10:00:00Z",
        "updated_at": f"2026-05-0{number}T11:00:00Z",
    }


@pytest.mark.asyncio
async def test_freshdesk_ticket_attachments_uses_config_auth_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_conversation(1)])

    adapter = FreshdeskTicketAttachmentsImportAdapter(
        config={
            "domain": "acme",
            "api_key": "freshdesk-key",
            "ticket_ids": ["42"],
            "updated_since": "2026-05-01T00:00:00Z",
            "per_page": 5,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert FreshdeskTicketAttachmentsAdapter is FreshdeskTicketAttachmentsImportAdapter
    assert adapter.domain == "acme.freshdesk.com"
    assert requests[0].url.path == "/api/v2/tickets/42/conversations"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "5"
    assert requests[0].url.params["updated_since"] == "2026-05-01T00:00:00Z"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "freshdesk-ticket-attachment:42:5001:7001"
    assert signal.source_adapter == "freshdesk_ticket_attachments_import"
    assert signal.source_type.value == "roadmap"
    assert signal.title == "Freshdesk ticket 42 attachment debug-1.txt"
    assert signal.content == "Plain body 1"
    assert signal.url == "https://acme.freshdesk.com/helpdesk/attachments/7001"
    assert signal.author == "9001"
    assert signal.metadata["ticket_id"] == "42"
    assert signal.metadata["conversation_id"] == 5001
    assert signal.metadata["attachment_id"] == 7001
    assert signal.metadata["filename"] == "debug-1.txt"
    assert signal.metadata["content_type"] == "text/plain"
    assert signal.metadata["size"] == 129
    assert signal.metadata["uploader"] == "9001"
    assert signal.metadata["attachment_url"] == "https://acme.freshdesk.com/helpdesk/attachments/7001"
    assert signal.metadata["raw"]["attachment"]["id"] == 7001


@pytest.mark.asyncio
async def test_freshdesk_ticket_attachments_discovers_recent_tickets_and_paginates() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v2/tickets" and request.url.params["page"] == "1":
            return httpx.Response(200, json=[{"id": 42}], headers={"Link": '<https://acme.freshdesk.com/api/v2/tickets?page=2>; rel="next"'})
        if request.url.path == "/api/v2/tickets":
            return httpx.Response(200, json=[{"id": 43}])
        if request.url.path.endswith("/tickets/42/conversations") and request.url.params["page"] == "1":
            return httpx.Response(200, json=[_conversation(1)])
        return httpx.Response(200, json=[_conversation(2)])

    adapter = FreshdeskTicketAttachmentsImportAdapter(
        domain="acme.freshdesk.com",
        api_key="freshdesk-key",
        config={"per_page": 1, "per_ticket_limit": 1, "updated_since": "2026-05-01T00:00:00Z"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.path for request in requests] == [
        "/api/v2/tickets",
        "/api/v2/tickets",
        "/api/v2/tickets/42/conversations",
        "/api/v2/tickets/43/conversations",
    ]
    assert [signal.metadata["ticket_id"] for signal in signals] == ["42", "43"]
    assert requests[0].url.params["updated_since"] == "2026-05-01T00:00:00Z"


@pytest.mark.asyncio
async def test_freshdesk_ticket_attachments_filters_private_and_supports_fallback_fields() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("page") == "1":
            return httpx.Response(200, json=[_conversation(1, private=True)])
        return httpx.Response(
            200,
            json=[
                _conversation(
                    2,
                    attachments=[
                        {
                            "filename": "trace.har",
                            "content_type": "application/json",
                            "file_size": 2048,
                            "url": "https://files.example/trace.har",
                        }
                    ],
                )
            ],
        )

    adapter = FreshdeskTicketAttachmentsImportAdapter(
        domain="acme",
        api_key="freshdesk-key",
        config={"ticket_id": 42, "per_page": 1, "per_ticket_limit": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert len(signals) == 1
    assert signals[0].id == "freshdesk-ticket-attachment:42:5002:https://files.example/trace.har"
    assert signals[0].metadata["filename"] == "trace.har"
    assert signals[0].metadata["size"] == 2048
    assert signals[0].metadata["private"] is False


@pytest.mark.asyncio
async def test_freshdesk_ticket_attachments_include_private_and_empty_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FRESHDESK_DOMAIN", raising=False)
    monkeypatch.delenv("FRESHDESK_API_KEY", raising=False)

    assert await FreshdeskTicketAttachmentsImportAdapter(config={"ticket_ids": ["42"]}).fetch() == []
    assert await FreshdeskTicketAttachmentsImportAdapter(domain="acme", api_key="key").fetch(limit=0) == []

    private = FreshdeskTicketAttachmentsImportAdapter(
        domain="acme",
        api_key="key",
        config={"ticket_ids": ["42"], "include_private": True},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[_conversation(1, private=True)]))),
    )
    assert (await private.fetch(limit=2))[0].metadata["private"] is True

    failing = FreshdeskTicketAttachmentsImportAdapter(
        domain="acme",
        api_key="key",
        config={"ticket_ids": ["42"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []
