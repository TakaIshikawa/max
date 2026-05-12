"""Tests for Zendesk ticket comments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.zendesk_ticket_comments_adapter import (
    ZendeskTicketCommentsAdapter,
    ZendeskTicketCommentsImportAdapter,
)


def _comment(number: int, *, public: bool = True, body: str | None = None) -> dict:
    return {
        "id": 7000 + number,
        "type": "Comment",
        "author_id": 9000 + number,
        "body": body if body is not None else f"Plain text body {number}",
        "html_body": f"<p>HTML body {number}</p>",
        "plain_body": f"Plain body {number}",
        "public": public,
        "audit_id": 8000 + number,
        "attachments": [{"id": "a"}, {"id": "b"}],
        "created_at": f"2026-05-0{number}T10:00:00Z",
    }


@pytest.mark.asyncio
async def test_zendesk_ticket_comments_builds_base_url_from_subdomain_and_maps_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "acme")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"comments": [_comment(1)], "next_page": None})

    adapter = ZendeskTicketCommentsImportAdapter(
        email="agent@example.com",
        token="api-token",
        config={"ticket_ids": ["42"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert ZendeskTicketCommentsAdapter is ZendeskTicketCommentsImportAdapter
    assert adapter.base_url == "https://acme.zendesk.com"
    assert requests[0].url == "https://acme.zendesk.com/api/v2/tickets/42/comments.json"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert len(signals) == 1
    assert signals[0].id == "zendesk-ticket-comment:42:7001"
    assert signals[0].source_adapter == "zendesk_ticket_comments_import"
    assert signals[0].source_type.value == "roadmap"
    assert signals[0].title == "Zendesk ticket 42 comment"
    assert signals[0].content == "Plain text body 1"
    assert signals[0].url == "https://acme.zendesk.com/agent/tickets/42"
    assert signals[0].author == "9001"
    assert signals[0].published_at is not None
    assert signals[0].metadata["ticket_id"] == "42"
    assert signals[0].metadata["comment_id"] == 7001
    assert signals[0].metadata["author_id"] == 9001
    assert signals[0].metadata["public"] is True
    assert signals[0].metadata["visibility"] == "public"
    assert signals[0].metadata["attachments_count"] == 2
    assert signals[0].metadata["audit_id"] == 8001
    assert signals[0].metadata["body"] == "Plain text body 1"
    assert signals[0].metadata["html_body"] == "<p>HTML body 1</p>"
    assert signals[0].metadata["created_at"] == "2026-05-01T10:00:00Z"


@pytest.mark.asyncio
async def test_zendesk_ticket_comments_follows_next_page_multiple_tickets_and_limit() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/v2/tickets/42/comments.json":
            return httpx.Response(
                200,
                json={
                    "comments": [_comment(1)],
                    "next_page": "https://max.zendesk.com/api/v2/tickets/42/comments/page2.json",
                },
            )
        if request.url.path == "/api/v2/tickets/42/comments/page2.json":
            return httpx.Response(200, json={"comments": [_comment(2, public=False)], "next_page": None})
        return httpx.Response(200, json={"comments": [_comment(3)], "next_page": None})

    adapter = ZendeskTicketCommentsImportAdapter(
        base_url="https://max.zendesk.com",
        email="agent@example.com",
        token="api-token",
        config={"ticket_ids": ["42", "43"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert paths == [
        "/api/v2/tickets/42/comments.json",
        "/api/v2/tickets/42/comments/page2.json",
        "/api/v2/tickets/43/comments.json",
    ]
    assert [signal.metadata["ticket_id"] for signal in signals] == ["42", "42", "43"]
    assert signals[1].metadata["visibility"] == "private"


@pytest.mark.asyncio
async def test_zendesk_ticket_comments_public_only_and_html_body_fallback() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "comments": [
                    _comment(1, public=False),
                    _comment(2, public=True, body=""),
                ],
                "next_page": None,
            },
        )

    adapter = ZendeskTicketCommentsImportAdapter(
        base_url="https://max.zendesk.com",
        email="agent@example.com",
        token="api-token",
        config={"ticket_id": 42, "include_public_only": True},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].metadata["comment_id"] == 7002
    assert signals[0].content == "<p>HTML body 2</p>"


@pytest.mark.asyncio
async def test_zendesk_ticket_comments_empty_without_required_config_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZENDESK_BASE_URL", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    monkeypatch.delenv("ZENDESK_EMAIL", raising=False)
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)

    assert await ZendeskTicketCommentsImportAdapter(config={"ticket_ids": ["42"]}).fetch() == []
    assert await ZendeskTicketCommentsImportAdapter(base_url="https://max.zendesk.com", email="agent@example.com", token="token").fetch() == []
    assert await ZendeskTicketCommentsImportAdapter(base_url="https://max.zendesk.com", email="agent@example.com", token="token", config={"ticket_ids": ["42"]}).fetch(limit=0) == []

    failing = ZendeskTicketCommentsImportAdapter(
        base_url="https://max.zendesk.com",
        email="agent@example.com",
        token="token",
        config={"ticket_ids": ["42"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )

    assert await failing.fetch(limit=2) == []
