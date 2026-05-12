"""Tests for Zendesk ticket satisfaction ratings import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.zendesk_ticket_satisfaction_ratings_adapter import (
    ZendeskTicketSatisfactionRatingsAdapter,
    ZendeskTicketSatisfactionRatingsImportAdapter,
)
from max.types.signal import SignalSourceType


def _rating(ticket_id: int = 42, rating_id: int = 7001, score: str = "good") -> dict:
    return {
        "id": rating_id,
        "score": score,
        "reason": "The response was helpful",
        "comment": "Fast and clear support.",
        "requester_id": 1234,
        "ticket_id": ticket_id,
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-01T11:00:00Z",
    }


@pytest.mark.asyncio
async def test_zendesk_ticket_satisfaction_ratings_basic_auth_maps_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "acme")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"satisfaction_rating": _rating()})

    adapter = ZendeskTicketSatisfactionRatingsImportAdapter(
        email="agent@example.com",
        api_token="api-token",
        config={"ticket_id": 42, "page_size": 25},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert ZendeskTicketSatisfactionRatingsAdapter is ZendeskTicketSatisfactionRatingsImportAdapter
    assert requests[0].url == "https://acme.zendesk.com/api/v2/tickets/42/satisfaction_rating.json?page%5Bsize%5D=25"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert requests[0].headers["User-Agent"] == "max-zendesk-ticket-satisfaction-ratings-import/1"
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "zendesk-ticket-satisfaction-rating:42:7001"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "zendesk_ticket_satisfaction_ratings_import"
    assert signal.title == "Zendesk ticket 42 satisfaction rating good"
    assert signal.content == "Score: good. Reason: The response was helpful. Fast and clear support."
    assert signal.url == "https://acme.zendesk.com/agent/tickets/42"
    assert signal.author == "1234"
    assert signal.published_at is not None
    assert signal.metadata["score"] == "good"
    assert signal.metadata["reason"] == "The response was helpful"
    assert signal.metadata["comment"] == "Fast and clear support."
    assert signal.metadata["ticket_id"] == 42
    assert signal.metadata["requester_id"] == 1234
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-01T11:00:00Z"
    assert signal.metadata["url"] == "https://acme.zendesk.com/agent/tickets/42"
    assert signal.metadata["raw"]["id"] == 7001
    assert "ticket-satisfaction-rating" in signal.tags
    assert "rating-good" in signal.tags


@pytest.mark.asyncio
async def test_zendesk_ticket_satisfaction_ratings_oauth_fetches_multiple_ticket_ids_and_honors_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        ticket_id = int(request.url.path.split("/")[4])
        return httpx.Response(200, json={"satisfaction_rating": _rating(ticket_id, ticket_id + 7000, "bad")})

    adapter = ZendeskTicketSatisfactionRatingsImportAdapter(
        base_url="https://max.zendesk.com/",
        oauth_token="oauth-token",
        config={"ticket_ids": [42, "43", 44]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert adapter.base_url == "https://max.zendesk.com"
    assert requests[0].headers["Authorization"] == "Bearer oauth-token"
    assert [request.url.path for request in requests] == [
        "/api/v2/tickets/42/satisfaction_rating.json",
        "/api/v2/tickets/43/satisfaction_rating.json",
    ]
    assert [signal.metadata["ticket_id"] for signal in signals] == [42, 43]
    assert all("rating-bad" in signal.tags for signal in signals)


@pytest.mark.asyncio
async def test_zendesk_ticket_satisfaction_ratings_empty_rating_response() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"satisfaction_rating": None})

    adapter = ZendeskTicketSatisfactionRatingsImportAdapter(
        base_url="https://max.zendesk.com",
        oauth_token="oauth-token",
        config={"ticket_ids": [42]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=5) == []
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_zendesk_ticket_satisfaction_ratings_empty_without_config_auth_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZENDESK_BASE_URL", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    monkeypatch.delenv("ZENDESK_EMAIL", raising=False)
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)
    monkeypatch.delenv("ZENDESK_OAUTH_TOKEN", raising=False)

    assert await ZendeskTicketSatisfactionRatingsImportAdapter(config={"ticket_ids": [42]}).fetch() == []
    assert await ZendeskTicketSatisfactionRatingsImportAdapter(base_url="https://max.zendesk.com", oauth_token="token").fetch() == []
    assert await ZendeskTicketSatisfactionRatingsImportAdapter(
        base_url="https://max.zendesk.com",
        config={"ticket_ids": [42]},
        email="agent@example.com",
    ).fetch() == []
    assert await ZendeskTicketSatisfactionRatingsImportAdapter(
        base_url="https://max.zendesk.com",
        oauth_token="token",
        config={"ticket_ids": [42]},
    ).fetch(limit=0) == []

    failing = ZendeskTicketSatisfactionRatingsImportAdapter(
        base_url="https://max.zendesk.com",
        oauth_token="token",
        config={"ticket_ids": [42]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []
