"""Tests for Datadog downtimes import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.datadog_downtimes_adapter import DatadogDowntimesAdapter


DOWNTIME = {
    "id": 123,
    "message": "Deploy window",
    "scope": ["env:prod", "service:api"],
    "monitor_id": 456,
    "monitor_tags": ["team:platform"],
    "start": 1710000000,
    "end": 1890000000,
    "created": 1709990000,
    "modified": 1710000100,
    "creator": {"id": 7, "handle": "ops@example.com", "name": "Ops"},
    "updater": {"id": 8, "handle": "sre@example.com", "name": "SRE"},
    "recurrence": {"type": "weeks", "period": 1},
    "tags": ["change:deploy"],
    "url": "https://app.datadoghq.com/monitors/downtimes/123",
}


@pytest.mark.asyncio
async def test_datadog_downtimes_fetch_maps_downtime_and_query_options() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[DOWNTIME])

    adapter = DatadogDowntimesAdapter(
        api_key="api",
        app_key="app",
        config={
            "site": "datadoghq.eu",
            "current_only": True,
            "monitor_id": 456,
            "scope": ["env:prod", "service:api"],
            "start": 1710000000,
            "end": 1890000000,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requests[0].url.host == "api.datadoghq.eu"
    assert requests[0].url.path == "/api/v1/downtime"
    assert requests[0].headers["DD-API-KEY"] == "api"
    assert requests[0].headers["DD-APPLICATION-KEY"] == "app"
    assert requests[0].url.params["current_only"] == "true"
    assert requests[0].url.params["monitor_id"] == "456"
    assert requests[0].url.params["scope"] == "env:prod,service:api"
    assert requests[0].url.params["start"] == "1710000000"
    assert requests[0].url.params["end"] == "1890000000"
    assert len(signals) == 1
    assert signals[0].id == "datadog-downtime-123"
    assert signals[0].source_adapter == "datadog_downtimes_import"
    assert signals[0].source_type.value == "failure_data"
    assert signals[0].content == "Deploy window"
    assert signals[0].url == DOWNTIME["url"]
    assert signals[0].author == "ops@example.com"
    assert signals[0].metadata["datadog_downtime_id"] == 123
    assert signals[0].metadata["scope"] == ["env:prod", "service:api"]
    assert signals[0].metadata["monitor_ids"] == [456]
    assert signals[0].metadata["monitor_tags"] == ["team:platform"]
    assert signals[0].metadata["status"] == "active"
    assert signals[0].metadata["active"] is True
    assert signals[0].metadata["canceled"] is False
    assert signals[0].metadata["disabled"] is False
    assert signals[0].metadata["creator"]["handle"] == "ops@example.com"
    assert signals[0].metadata["updater"]["handle"] == "sre@example.com"
    assert signals[0].metadata["recurrence"] == {"type": "weeks", "period": 1}
    assert signals[0].metadata["tags"] == ["change:deploy"]


@pytest.mark.asyncio
async def test_datadog_downtimes_caps_results_to_limit_and_maps_statuses() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {**DOWNTIME, "id": 1, "canceled": True},
                {**DOWNTIME, "id": 2, "disabled": True},
                {**DOWNTIME, "id": 3},
            ],
        )

    adapter = DatadogDowntimesAdapter(
        api_key="api",
        app_key="app",
        config={"limit": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["datadog_downtime_id"] for signal in signals] == [1, 2]
    assert [signal.metadata["status"] for signal in signals] == ["canceled", "disabled"]


@pytest.mark.asyncio
async def test_datadog_downtimes_missing_keys_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATADOG_API_KEY", raising=False)
    monkeypatch.delenv("DD_API_KEY", raising=False)
    monkeypatch.delenv("DATADOG_APP_KEY", raising=False)
    monkeypatch.delenv("DATADOG_APPLICATION_KEY", raising=False)
    monkeypatch.delenv("DD_APPLICATION_KEY", raising=False)

    assert await DatadogDowntimesAdapter().fetch() == []


@pytest.mark.asyncio
async def test_datadog_downtimes_reads_env_keys_and_handles_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DD_API_KEY", "env-api")
    monkeypatch.setenv("DD_APPLICATION_KEY", "env-app")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(403)

    adapter = DatadogDowntimesAdapter(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    assert await adapter.fetch(limit=3) == []
    assert requests[0].headers["DD-API-KEY"] == "env-api"
    assert requests[0].headers["DD-APPLICATION-KEY"] == "env-app"
