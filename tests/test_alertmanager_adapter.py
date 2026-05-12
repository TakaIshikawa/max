"""Tests for Prometheus Alertmanager alert import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.alertmanager_adapter import AlertmanagerAdapter


@pytest.mark.asyncio
async def test_alertmanager_fetch_maps_active_alert_and_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "labels": {"alertname": "HighErrorRate", "severity": "critical", "service": "api"},
                    "annotations": {"summary": "High error rate", "description": "API 5xx rate is above threshold"},
                    "startsAt": "2026-05-12T01:00:00Z",
                    "endsAt": "0001-01-01T00:00:00Z",
                    "generatorURL": "https://prometheus.test/graph?g0.expr=errors",
                    "fingerprint": "abc123",
                    "receivers": [{"name": "platform"}],
                    "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
                }
            ],
        )

    adapter = AlertmanagerAdapter(
        base_url="https://alertmanager.test",
        bearer_token="token",
        config={"receiver": "platform", "label_filters": {"service": "api"}},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await adapter.fetch(limit=5)

    assert requests[0].headers["Authorization"] == "Bearer token"
    assert requests[0].url.params["active"] == "true"
    assert requests[0].url.params["silenced"] == "false"
    assert requests[0].url.params["receiver"] == "platform"
    assert requests[0].url.params["filter"] == 'service="api"'
    assert len(signals) == 1
    assert signals[0].title == "High error rate"
    assert signals[0].content == "API 5xx rate is above threshold"
    assert signals[0].url == "https://prometheus.test/graph?g0.expr=errors"
    assert signals[0].metadata["severity"] == "critical"
    assert signals[0].metadata["status"]["state"] == "active"
    assert signals[0].metadata["receivers"] == ["platform"]
    assert signals[0].metadata["fingerprint"] == "abc123"
    assert signals[0].metadata["generator_url"] == "https://prometheus.test/graph?g0.expr=errors"
    assert signals[0].metadata["starts_at"] == "2026-05-12T01:00:00Z"
    assert signals[0].metadata["ends_at"] == "0001-01-01T00:00:00Z"
    assert signals[0].metadata["labels"]["service"] == "api"
    assert signals[0].metadata["annotations"]["summary"] == "High error rate"


@pytest.mark.asyncio
async def test_alertmanager_fetch_includes_silenced_alerts() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["silenced"] == "true"
        return httpx.Response(
            200,
            json=[
                {
                    "labels": {"alertname": "DiskFull", "severity": "warning"},
                    "annotations": {"summary": "Disk nearly full"},
                    "fingerprint": "silenced",
                    "status": {"state": "suppressed", "silencedBy": ["silence-1"]},
                }
            ],
        )

    adapter = AlertmanagerAdapter(base_url="https://alertmanager.test", config={"include_silenced": True}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch()

    assert signals[0].title == "Disk nearly full"
    assert signals[0].metadata["silence_ids"] == ["silence-1"]
    assert signals[0].metadata["state"] == "suppressed"


@pytest.mark.asyncio
async def test_alertmanager_missing_annotations_falls_back_to_alertname_and_labels() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"labels": {"alertname": "InstanceDown", "instance": "api-1"}, "fingerprint": "fp"}])

    adapter = AlertmanagerAdapter(base_url="https://alertmanager.test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch()

    assert signals[0].title == "InstanceDown"
    assert signals[0].content == "InstanceDown"
    assert signals[0].metadata["annotations"] == {}


@pytest.mark.asyncio
async def test_alertmanager_http_failure_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = AlertmanagerAdapter(base_url="https://alertmanager.test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch() == []


@pytest.mark.asyncio
async def test_alertmanager_missing_base_url_returns_empty() -> None:
    assert await AlertmanagerAdapter().fetch() == []
