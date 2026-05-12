"""Tests for Datadog monitors import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.datadog_monitors_adapter import DatadogMonitorsAdapter


MONITOR = {
    "id": 123,
    "name": "API latency high",
    "message": "p95 latency is above threshold",
    "query": "avg(last_5m):avg:api.latency{env:prod} > 500",
    "type": "metric alert",
    "overall_state": "Alert",
    "priority": 2,
    "tags": ["service:api", "env:prod"],
    "monitor_tags": ["team:platform"],
    "created": "2026-05-01T10:00:00Z",
    "modified": 1778547600,
    "creator": {"id": 7, "handle": "ops@example.com", "name": "Ops"},
    "options": {"thresholds": {"critical": 500}},
    "url": "https://app.datadoghq.com/monitors/123",
}


@pytest.mark.asyncio
async def test_datadog_monitors_fetch_maps_monitor_and_query_options() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[MONITOR])

    adapter = DatadogMonitorsAdapter(
        api_key="api",
        app_key="app",
        config={
            "site": "datadoghq.eu",
            "tags": ["env:prod"],
            "monitor_tags": ["team:platform"],
            "group_states": "all",
            "name": "latency",
            "with_downtimes": True,
            "page_size": 50,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requests[0].url.host == "api.datadoghq.eu"
    assert requests[0].url.path == "/api/v1/monitor"
    assert requests[0].headers["DD-API-KEY"] == "api"
    assert requests[0].headers["DD-APPLICATION-KEY"] == "app"
    assert requests[0].url.params["tags"] == "env:prod"
    assert requests[0].url.params["monitor_tags"] == "team:platform"
    assert requests[0].url.params["group_states"] == "all"
    assert requests[0].url.params["name"] == "latency"
    assert requests[0].url.params["with_downtimes"] == "true"
    assert requests[0].url.params["page"] == "0"
    assert requests[0].url.params["page_size"] == "5"
    assert len(signals) == 1
    assert signals[0].id == "datadog-monitor-123"
    assert signals[0].title == "API latency high Alert"
    assert signals[0].content == "p95 latency is above threshold"
    assert signals[0].url == MONITOR["url"]
    assert signals[0].author == "ops@example.com"
    assert signals[0].metadata["datadog_monitor_id"] == 123
    assert signals[0].metadata["overall_state"] == "Alert"
    assert signals[0].metadata["priority"] == 2
    assert signals[0].metadata["query"] == MONITOR["query"]
    assert signals[0].metadata["tags"] == ["service:api", "env:prod"]
    assert signals[0].metadata["monitor_tags"] == ["team:platform"]
    assert signals[0].metadata["options"] == {"thresholds": {"critical": 500}}


@pytest.mark.asyncio
async def test_datadog_monitors_filters_status_and_paginates_to_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["page"] == "0":
            return httpx.Response(
                200,
                json=[
                    {**MONITOR, "id": 1, "overall_state": "OK"},
                    {**MONITOR, "id": 2, "overall_state": "Alert"},
                ],
            )
        return httpx.Response(
            200,
            json=[
                {**MONITOR, "id": 3, "overall_state": "Warn"},
                {**MONITOR, "id": 4, "overall_state": "Alert"},
            ],
        )

    adapter = DatadogMonitorsAdapter(
        api_key="api",
        app_key="app",
        config={"status": ["Alert", "Warn"], "page_size": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert [signal.metadata["datadog_monitor_id"] for signal in signals] == [2, 3, 4]
    assert [request.url.params["page"] for request in requests] == ["0", "1"]
    assert [request.url.params["page_size"] for request in requests] == ["2", "2"]


@pytest.mark.asyncio
async def test_datadog_monitors_missing_keys_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATADOG_API_KEY", raising=False)
    monkeypatch.delenv("DD_API_KEY", raising=False)
    monkeypatch.delenv("DATADOG_APP_KEY", raising=False)
    monkeypatch.delenv("DATADOG_APPLICATION_KEY", raising=False)
    monkeypatch.delenv("DD_APPLICATION_KEY", raising=False)

    assert await DatadogMonitorsAdapter().fetch() == []


@pytest.mark.asyncio
async def test_datadog_monitors_http_failure_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    adapter = DatadogMonitorsAdapter(
        api_key="api",
        app_key="app",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch() == []
