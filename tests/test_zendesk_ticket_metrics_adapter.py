"""Tests for Zendesk ticket metrics import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.zendesk_ticket_metrics_adapter import (
    ZendeskTicketMetricsAdapter,
    ZendeskTicketMetricsImportAdapter,
)
from max.types.signal import SignalSourceType


def _metric(ticket_id: int, *, metric_id: int | None = None, breached: bool = False, updated_at: str = "2026-05-12T10:00:00Z") -> dict:
    return {
        "id": metric_id or ticket_id + 1000,
        "ticket_id": ticket_id,
        "reply_time_in_minutes": {"calendar": 9, "business": 5, "breached": breached},
        "first_resolution_time_in_minutes": {"calendar": 120, "business": 90},
        "full_resolution_time_in_minutes": {"calendar": 240, "business": 180, "breached": breached},
        "requester_wait_time_in_minutes": {"calendar": 60, "business": 35},
        "agent_wait_time_in_minutes": {"calendar": 12, "business": 8},
        "on_hold_time_in_minutes": {"calendar": 30, "business": 20},
        "reopens": 1,
        "replies": 3,
        "created_at": "2026-05-10T10:00:00Z",
        "updated_at": updated_at,
    }


@pytest.mark.asyncio
async def test_zendesk_ticket_metrics_fetches_configured_ticket_ids_and_maps_sla_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "acme")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        ticket_id = int(request.url.path.split("/")[4])
        return httpx.Response(200, json={"ticket_metric": _metric(ticket_id, breached=True)})

    adapter = ZendeskTicketMetricsImportAdapter(
        email="agent@example.com",
        token="api-token",
        config={"ticket_ids": ["42", "43"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert ZendeskTicketMetricsAdapter is ZendeskTicketMetricsImportAdapter
    assert adapter.base_url == "https://acme.zendesk.com"
    assert [request.url.path for request in requests] == [
        "/api/v2/tickets/42/metrics.json",
        "/api/v2/tickets/43/metrics.json",
    ]
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert [signal.metadata["ticket_id"] for signal in signals] == [42, 43]
    signal = signals[0]
    assert signal.id == "zendesk-ticket-metric:42:1042"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "zendesk_ticket_metrics_import"
    assert signal.title == "Zendesk ticket 42 SLA metrics"
    assert signal.url == "https://acme.zendesk.com/agent/tickets/42"
    assert signal.published_at is not None
    assert signal.metadata["metric_set_id"] == 1042
    assert signal.metadata["reply_time"] == {"calendar": 9, "business": 5}
    assert signal.metadata["full_resolution_time"] == {"calendar": 240, "business": 180}
    assert signal.metadata["requester_wait_time"] == {"calendar": 60, "business": 35}
    assert signal.metadata["agent_wait_time"] == {"calendar": 12, "business": 8}
    assert signal.metadata["on_hold_time"] == {"calendar": 30, "business": 20}
    assert signal.metadata["breached"] is True
    assert signal.metadata["breach_flags"]["reply_time_in_minutes.breached"] is True
    assert signal.metadata["updated_at"] == "2026-05-12T10:00:00Z"
    assert "sla-breach" in signal.tags


@pytest.mark.asyncio
async def test_zendesk_ticket_metrics_fetches_recent_metrics_and_applies_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "ticket_metrics": [
                        _metric(10, breached=False, updated_at="2026-05-11T10:00:00Z"),
                        _metric(11, breached=True, updated_at="2026-05-12T10:00:00Z"),
                    ],
                    "next_page": "https://max.zendesk.com/api/v2/ticket_metrics.json?page=2",
                },
            )
        return httpx.Response(
            200,
            json={
                "ticket_metrics": [
                    _metric(12, breached=True, updated_at="2026-05-09T10:00:00Z"),
                    _metric(13, breached=True, updated_at="2026-05-13T10:00:00Z"),
                ],
                "next_page": None,
            },
        )

    adapter = ZendeskTicketMetricsImportAdapter(
        base_url="https://max.zendesk.com",
        email="agent@example.com",
        token="api-token",
        config={"page_size": 2, "breached_only": True, "updated_since": "2026-05-10T00:00:00Z"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=4)

    assert [request.url.path for request in requests] == [
        "/api/v2/ticket_metrics.json",
        "/api/v2/ticket_metrics.json",
    ]
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].url.params["updated_since"] == "2026-05-10T00:00:00Z"
    assert [signal.metadata["ticket_id"] for signal in signals] == [11, 13]


@pytest.mark.asyncio
async def test_zendesk_ticket_metrics_empty_without_required_config_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZENDESK_BASE_URL", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    monkeypatch.delenv("ZENDESK_EMAIL", raising=False)
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)

    assert await ZendeskTicketMetricsImportAdapter(config={"ticket_ids": ["42"]}).fetch() == []
    assert await ZendeskTicketMetricsImportAdapter(base_url="https://max.zendesk.com", email="agent@example.com", token="token").fetch(limit=0) == []

    failing = ZendeskTicketMetricsImportAdapter(
        base_url="https://max.zendesk.com",
        email="agent@example.com",
        token="token",
        config={"ticket_ids": ["42"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )

    assert await failing.fetch(limit=2) == []
