"""Tests for PagerDuty incident alerts import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.pagerduty_incident_alerts_adapter import PagerDutyIncidentAlertsAdapter


def _alert(alert_id: str = "PALERT1", *, status: str = "triggered") -> dict:
    return {
        "id": alert_id,
        "summary": "Worker queue latency high",
        "status": status,
        "severity": "critical",
        "alert_key": "queue-latency",
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-01T10:05:00Z",
        "html_url": "https://acme.pagerduty.com/alerts/PALERT1",
        "service": {
            "id": "PSVC1",
            "summary": "API Service",
            "type": "service_reference",
            "html_url": "https://acme.pagerduty.com/services/PSVC1",
        },
        "incident": {
            "id": "PINC1",
            "summary": "API latency incident",
            "type": "incident_reference",
            "html_url": "https://acme.pagerduty.com/incidents/PINC1",
        },
        "body": {"details": {"message": "p95 latency exceeded threshold"}},
    }


@pytest.mark.asyncio
async def test_pagerduty_incident_alerts_fetches_maps_and_uses_headers() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"alerts": [_alert()], "more": False})

    adapter = PagerDutyIncidentAlertsAdapter(
        api_token="pd-token",
        api_url="https://api.pagerduty.test",
        config={"incident_ids": ["PINC1"], "statuses": ["triggered"], "services": ["PSVC1"], "page_size": 25},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=30)

    assert len(requests) == 1
    assert requests[0].url.path == "/incidents/PINC1/alerts"
    assert requests[0].url.params["limit"] == "25"
    assert requests[0].url.params["offset"] == "0"
    assert requests[0].url.params["statuses[]"] == "triggered"
    assert requests[0].url.params["service_ids[]"] == "PSVC1"
    assert requests[0].headers["Authorization"] == "Token token=pd-token"
    assert requests[0].headers["Accept"] == "application/vnd.pagerduty+json;version=2"
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "pagerduty-alert:PINC1:PALERT1"
    assert signal.source_adapter == "pagerduty_incident_alerts_import"
    assert signal.source_type.value == "failure_data"
    assert signal.title == "Worker queue latency high"
    assert "p95 latency exceeded threshold" in signal.content
    assert signal.url == "https://acme.pagerduty.com/alerts/PALERT1"
    assert signal.metadata["pagerduty_alert_id"] == "PALERT1"
    assert signal.metadata["pagerduty_incident_id"] == "PINC1"
    assert signal.metadata["service"]["id"] == "PSVC1"
    assert signal.metadata["incident"]["id"] == "PINC1"
    assert "alert" in signal.tags


@pytest.mark.asyncio
async def test_pagerduty_incident_alerts_paginates_offset_and_honors_limit_per_incident() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/incidents/PINC2/alerts":
            return httpx.Response(200, json={"alerts": [_alert("PALERT3")], "limit": 1, "offset": 0, "more": False})
        if request.url.params["offset"] == "0":
            return httpx.Response(200, json={"alerts": [_alert("PALERT1")], "limit": 1, "offset": 0, "more": True})
        return httpx.Response(200, json={"alerts": [_alert("PALERT2"), _alert("PALERT3")], "limit": 1, "offset": 1, "more": False})

    adapter = PagerDutyIncidentAlertsAdapter(
        api_token="pd-token",
        config={"incident_ids": ["PINC1", "PINC2"], "page_size": 1, "limit_per_incident": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert [request.url.params["offset"] for request in requests] == ["0", "1", "0"]
    assert [signal.metadata["pagerduty_alert_id"] for signal in signals] == ["PALERT1", "PALERT2", "PALERT3"]


@pytest.mark.asyncio
async def test_pagerduty_incident_alerts_empty_without_config_auth_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAGERDUTY_API_TOKEN", raising=False)

    assert await PagerDutyIncidentAlertsAdapter(config={"incident_ids": ["PINC1"]}).fetch() == []
    assert await PagerDutyIncidentAlertsAdapter(api_token="token").fetch() == []
    assert await PagerDutyIncidentAlertsAdapter(api_token="token", config={"incident_ids": ["PINC1"]}).fetch(limit=0) == []

    failing = PagerDutyIncidentAlertsAdapter(
        api_token="token",
        config={"incident_ids": ["PINC1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []
