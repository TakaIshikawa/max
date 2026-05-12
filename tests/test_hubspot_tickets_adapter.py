"""Tests for HubSpot tickets import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_tickets_adapter import HubSpotTicketsAdapter


def _ticket(number: int, *, subject: str | None = None) -> dict:
    return {
        "id": f"ticket-{number}",
        "archived": False,
        "createdAt": "2026-05-01T10:00:00Z",
        "updatedAt": "2026-05-02T10:00:00Z",
        "properties": {
            "subject": subject or f"Support ticket {number}",
            "content": f"Customer issue {number}",
            "hs_pipeline": "support",
            "hs_pipeline_stage": "triage",
            "hs_ticket_priority": "HIGH",
            "hs_ticket_category": "PRODUCT_ISSUE",
            "createdate": "2026-05-01T10:00:00Z",
            "hs_lastmodifieddate": "2026-05-02T10:00:00Z",
            "hubspot_owner_id": "owner-1",
        },
    }


@pytest.mark.asyncio
async def test_hubspot_tickets_fetches_pages_and_maps_metadata() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"results": [_ticket(1)], "paging": {"next": {"after": "cursor-2"}}},
            )
        return httpx.Response(200, json={"results": [_ticket(2)]})

    adapter = HubSpotTicketsAdapter(
        token="hubspot_token",
        api_url="https://hubspot.example",
        config={"limit": 1, "archived": False, "after": "cursor-1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer hubspot_token"
    assert requests[0].url.path == "/crm/v3/objects/tickets"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["archived"] == "false"
    assert requests[0].url.params["after"] == "cursor-1"
    assert requests[1].url.params["after"] == "cursor-2"
    assert set(requests[0].url.params.get_list("properties")) >= {
        "subject",
        "content",
        "hs_pipeline",
        "hs_pipeline_stage",
        "hs_ticket_priority",
        "hs_ticket_category",
        "createdate",
        "hs_lastmodifieddate",
    }
    assert [signal.metadata["ticket_id"] for signal in signals] == ["ticket-1", "ticket-2"]
    assert signals[0].source_adapter == "hubspot_tickets_import"
    assert signals[0].source_type.value == "market"
    assert signals[0].title == "Support ticket 1"
    assert signals[0].content == "Customer issue 1"
    assert signals[0].author == "owner-1"
    assert signals[0].metadata["pipeline"] == "support"
    assert signals[0].metadata["stage"] == "triage"
    assert signals[0].metadata["priority"] == "HIGH"
    assert signals[0].metadata["category"] == "PRODUCT_ISSUE"
    assert signals[0].metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signals[0].metadata["updated_at"] == "2026-05-02T10:00:00Z"
    assert "ticket" in signals[0].tags


@pytest.mark.asyncio
async def test_hubspot_tickets_uses_configured_properties_and_env_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "env_token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_ticket(1, subject="Escalation")]})

    adapter = HubSpotTicketsAdapter(
        api_url="https://hubspot.example",
        config={"properties": ["subject", "content", "hubspot_owner_id"], "archived": "true"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env_token"
    assert requests[0].url.params.get_list("properties") == [
        "subject",
        "content",
        "hubspot_owner_id",
    ]
    assert requests[0].url.params["archived"] == "true"
    assert signals[0].title == "Escalation"


@pytest.mark.asyncio
async def test_hubspot_tickets_empty_without_credentials_or_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)

    assert await HubSpotTicketsAdapter().fetch() == []
    assert await HubSpotTicketsAdapter(token="token").fetch(limit=0) == []


@pytest.mark.asyncio
async def test_hubspot_tickets_api_or_non_json_failure_returns_empty() -> None:
    async def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    failing = HubSpotTicketsAdapter(
        token="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(failing_handler)),
    )
    assert await failing.fetch(limit=2) == []

    async def non_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="nope")

    non_json = HubSpotTicketsAdapter(
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(non_json_handler)),
    )
    assert await non_json.fetch(limit=2) == []
