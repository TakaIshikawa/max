"""Tests for PagerDuty incident log entries import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.pagerduty_incident_log_entries_adapter import PagerDutyIncidentLogEntriesAdapter


def _entry(entry_id: str = "PLE1") -> dict:
    return {
        "id": entry_id,
        "type": "trigger_log_entry",
        "summary": "Incident triggered",
        "created_at": "2026-05-01T10:00:00Z",
        "html_url": "https://acme.pagerduty.com/log_entries/PLE1",
        "agent": {"id": "USER1", "summary": "On Call", "type": "user_reference"},
        "channel": {"type": "api", "summary": "Events API"},
        "incident": {"id": "PINC1", "summary": "API latency", "html_url": "https://acme.pagerduty.com/incidents/PINC1"},
        "details": {"message": "p95 exceeded"},
    }


@pytest.mark.asyncio
async def test_pagerduty_log_entries_fetches_maps_and_uses_headers() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"log_entries": [_entry()], "more": False})

    adapter = PagerDutyIncidentLogEntriesAdapter(
        token="pd-token",
        api_url="https://api.pagerduty.test",
        config={"incident_ids": ["PINC1"], "per_page": 25},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=30)

    assert requests[0].url.path == "/incidents/PINC1/log_entries"
    assert requests[0].url.params["limit"] == "25"
    assert requests[0].headers["Authorization"] == "Token token=pd-token"
    assert requests[0].headers["User-Agent"] == "max-pagerduty-incident-log-entries-import/1"
    signal = signals[0]
    assert signal.id == "pagerduty-log-entry:PINC1:PLE1"
    assert signal.source_adapter == "pagerduty_incident_log_entries_import"
    assert signal.title == "Incident triggered"
    assert "p95 exceeded" in signal.content
    assert signal.author == "On Call"
    assert signal.metadata["pagerduty_log_entry_id"] == "PLE1"
    assert signal.metadata["channel"]["summary"] == "Events API"


@pytest.mark.asyncio
async def test_pagerduty_log_entries_paginates_offset_and_respects_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["offset"] == "0":
            return httpx.Response(200, json={"log_entries": [_entry("PLE1")], "limit": 1, "offset": 0, "more": True})
        return httpx.Response(200, json={"log_entries": [_entry("PLE2")], "limit": 1, "offset": 1, "more": False})

    adapter = PagerDutyIncidentLogEntriesAdapter(
        api_token="pd-token",
        config={"incident_ids": ["PINC1", "PINC2"], "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["offset"] for request in requests] == ["0", "1"]
    assert [signal.metadata["pagerduty_log_entry_id"] for signal in signals] == ["PLE1", "PLE2"]


@pytest.mark.asyncio
async def test_pagerduty_log_entries_empty_without_config_auth_or_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAGERDUTY_API_TOKEN", raising=False)

    assert await PagerDutyIncidentLogEntriesAdapter(config={"incident_ids": ["PINC1"]}).fetch() == []
    assert await PagerDutyIncidentLogEntriesAdapter(token="token").fetch() == []
    assert await PagerDutyIncidentLogEntriesAdapter(token="token", config={"incident_ids": ["PINC1"]}).fetch(limit=0) == []

    failing = PagerDutyIncidentLogEntriesAdapter(
        token="token",
        config={"incident_ids": ["PINC1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []
