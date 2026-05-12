"""Tests for PagerDuty on-calls import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.pagerduty_oncalls_adapter import PagerDutyOnCallsAdapter


def _oncall(number: int) -> dict:
    return {
        "user": {
            "id": f"PUSER{number}",
            "summary": f"Responder {number}",
            "html_url": f"https://acme.pagerduty.com/users/PUSER{number}",
        },
        "schedule": {
            "id": "PSCHED1",
            "summary": "Primary schedule",
            "html_url": "https://acme.pagerduty.com/schedules/PSCHED1",
        },
        "escalation_policy": {
            "id": "PEP1",
            "summary": "API policy",
            "html_url": "https://acme.pagerduty.com/escalation_policies/PEP1",
        },
        "escalation_level": 1,
        "start": f"2026-05-{number:02d}T00:00:00Z",
        "end": f"2026-05-{number + 1:02d}T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_pagerduty_oncalls_fetches_filters_paginates_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"oncalls": [_oncall(1)], "limit": 1, "offset": 0, "more": True})
        return httpx.Response(200, json={"oncalls": [_oncall(2)], "limit": 1, "offset": 1, "more": False})

    adapter = PagerDutyOnCallsAdapter(
        api_token="pd-token",
        from_email="max@example.com",
        api_url="https://api.pagerduty.test",
        config={
            "schedule_ids": ["PSCHED1"],
            "escalation_policy_ids": ["PEP1"],
            "user_ids": ["PUSER1"],
            "since": "2026-05-01T00:00:00Z",
            "until": "2026-05-03T00:00:00Z",
            "earliest": "true",
            "per_page": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["offset"] for request in requests] == ["0", "1"]
    assert requests[0].url.path == "/oncalls"
    assert requests[0].headers["Authorization"] == "Token token=pd-token"
    assert requests[0].headers["From"] == "max@example.com"
    assert requests[0].url.params["schedule_ids[]"] == "PSCHED1"
    assert requests[0].url.params["escalation_policy_ids[]"] == "PEP1"
    assert requests[0].url.params["user_ids[]"] == "PUSER1"
    assert requests[0].url.params["since"] == "2026-05-01T00:00:00Z"
    assert requests[0].url.params["until"] == "2026-05-03T00:00:00Z"
    assert requests[0].url.params["earliest"] == "true"
    assert requests[0].url.params["limit"] == "1"
    assert len(signals) == 2
    assert signals[0].source_adapter == "pagerduty_oncalls_import"
    assert signals[0].source_type.value == "failure_data"
    assert signals[0].title == "Responder 1 on call"
    assert signals[0].author == "Responder 1"
    assert signals[0].url == "https://acme.pagerduty.com/schedules/PSCHED1"
    assert signals[0].metadata["pagerduty_user"]["id"] == "PUSER1"
    assert signals[0].metadata["pagerduty_schedule"]["id"] == "PSCHED1"
    assert signals[0].metadata["pagerduty_escalation_policy"]["id"] == "PEP1"
    assert signals[0].metadata["escalation_level"] == 1
    assert signals[0].metadata["start"] == "2026-05-01T00:00:00Z"
    assert signals[0].metadata["end"] == "2026-05-02T00:00:00Z"
    assert "operations" in signals[0].tags


@pytest.mark.asyncio
async def test_pagerduty_oncalls_reads_env_token_and_caps_config_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAGERDUTY_API_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"oncalls": [_oncall(1), _oncall(2)], "more": False})

    adapter = PagerDutyOnCallsAdapter(
        config={"limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert requests[0].headers["Authorization"] == "Token token=env-token"
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_pagerduty_oncalls_missing_token_non_positive_limit_and_failures_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAGERDUTY_API_TOKEN", raising=False)
    monkeypatch.delenv("PAGERDUTY_TOKEN", raising=False)

    assert await PagerDutyOnCallsAdapter().fetch() == []
    assert await PagerDutyOnCallsAdapter(api_token="pd-token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = PagerDutyOnCallsAdapter(
        api_token="pd-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch(limit=2) == []
