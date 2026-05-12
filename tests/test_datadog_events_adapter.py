"""Tests for Datadog events import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.datadog_events_adapter import DatadogEventsAdapter


@pytest.mark.asyncio
async def test_datadog_events_fetch_maps_event_and_query_options() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "events": [
                    {
                        "id": 123,
                        "title": "Monitor recovered",
                        "text": "Latency returned to normal",
                        "url": "https://app.datadoghq.com/event/event?id=123",
                        "tags": ["service:api", "env:prod"],
                        "alert_type": "success",
                        "priority": "normal",
                        "source_type_name": "monitor",
                        "host": "api-1",
                        "aggregation_key": "agg",
                        "date_happened": 1778547600,
                        "monitor_id": 42,
                    }
                ]
            },
        )

    adapter = DatadogEventsAdapter(
        api_key="api",
        app_key="app",
        config={"site": "datadoghq.eu", "query": "source:monitor", "from_ts": 1778540000, "to_ts": 1778550000, "tags": ["env:prod"], "limit": 10},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await adapter.fetch(limit=5)

    assert requests[0].url.host == "api.datadoghq.eu"
    assert requests[0].headers["DD-API-KEY"] == "api"
    assert requests[0].headers["DD-APPLICATION-KEY"] == "app"
    assert requests[0].url.params["start"] == "1778540000"
    assert requests[0].url.params["end"] == "1778550000"
    assert requests[0].url.params["filter"] == "source:monitor tags:env:prod"
    assert requests[0].url.params["limit"] == "5"
    assert signals[0].title == "Monitor recovered"
    assert signals[0].content == "Latency returned to normal"
    assert signals[0].metadata["tags"] == ["service:api", "env:prod"]
    assert signals[0].metadata["alert_type"] == "success"
    assert signals[0].metadata["priority"] == "normal"
    assert signals[0].metadata["source_type_name"] == "monitor"
    assert signals[0].metadata["host"] == "api-1"
    assert signals[0].metadata["aggregation_key"] == "agg"
    assert signals[0].metadata["monitor_id"] == 42
    assert signals[0].metadata["date_happened"] == 1778547600


@pytest.mark.asyncio
async def test_datadog_events_http_failure_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    adapter = DatadogEventsAdapter(api_key="api", app_key="app", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch() == []


@pytest.mark.asyncio
async def test_datadog_events_missing_keys_returns_empty() -> None:
    assert await DatadogEventsAdapter().fetch() == []
