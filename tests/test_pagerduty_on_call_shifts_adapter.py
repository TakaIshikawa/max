"""Tests for PagerDuty on-call shifts import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.pagerduty_on_call_shifts_adapter import PagerDutyOnCallShiftAdapter, PagerDutyOnCallShiftsAdapter


def _shift(number: int) -> dict:
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
async def test_fetches_on_call_shifts_with_auth_filters_pagination_and_mapping() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"oncalls": [_shift(1)], "limit": 1, "offset": 0, "more": True})
        return httpx.Response(200, json={"oncalls": [_shift(2)], "limit": 1, "offset": 1, "more": False})

    adapter = PagerDutyOnCallShiftsAdapter(
        token="pd-token",
        api_url="https://api.pagerduty.test",
        config={
            "schedule_ids": ["PSCHED1"],
            "escalation_policy_ids": ["PEP1"],
            "since": "2026-05-01T00:00:00Z",
            "until": "2026-05-03T00:00:00Z",
            "per_page": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert PagerDutyOnCallShiftAdapter is PagerDutyOnCallShiftsAdapter
    assert [request.url.params["offset"] for request in requests] == ["0", "1"]
    assert requests[0].url.path == "/oncalls"
    assert requests[0].headers["Authorization"] == "Token token=pd-token"
    assert requests[0].headers["User-Agent"] == "max-pagerduty-on-call-shifts-import/1"
    assert requests[0].url.params["schedule_ids[]"] == "PSCHED1"
    assert requests[0].url.params["escalation_policy_ids[]"] == "PEP1"
    assert requests[0].url.params["since"] == "2026-05-01T00:00:00Z"
    assert requests[0].url.params["until"] == "2026-05-03T00:00:00Z"
    assert requests[0].url.params["limit"] == "1"
    assert len(signals) == 2
    assert signals[0].id == "pagerduty-on-call-shift:PUSER1:PSCHED1:PEP1:1:2026-05-01T00:00:00Z:2026-05-02T00:00:00Z"
    assert signals[0].source_adapter == "pagerduty_on_call_shifts_import"
    assert signals[0].source_type.value == "failure_data"
    assert signals[0].title == "Responder 1 PagerDuty on-call shift"
    assert signals[0].author == "Responder 1"
    assert signals[0].url == "https://acme.pagerduty.com/schedules/PSCHED1"
    assert signals[0].published_at is not None
    assert signals[0].metadata["pagerduty_user"]["id"] == "PUSER1"
    assert signals[0].metadata["pagerduty_schedule"]["id"] == "PSCHED1"
    assert signals[0].metadata["pagerduty_escalation_policy"]["id"] == "PEP1"
    assert signals[0].metadata["escalation_level"] == 1
    assert signals[0].metadata["start"] == "2026-05-01T00:00:00Z"
    assert signals[0].metadata["end"] == "2026-05-02T00:00:00Z"
    assert signals[0].metadata["raw"]["user"]["id"] == "PUSER1"
    assert "shift" in signals[0].tags


@pytest.mark.asyncio
async def test_accepts_singular_filter_config_keys_and_empty_responses() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"oncalls": [], "more": False})

    adapter = PagerDutyOnCallShiftsAdapter(
        api_token="pd-token",
        config={"schedule_id": "PSCHED1", "escalation_policy_id": "PEP1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=5) == []
    assert requests[0].url.params["schedule_ids[]"] == "PSCHED1"
    assert requests[0].url.params["escalation_policy_ids[]"] == "PEP1"


@pytest.mark.asyncio
async def test_missing_token_non_positive_limit_and_non_2xx_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAGERDUTY_API_TOKEN", raising=False)

    assert await PagerDutyOnCallShiftsAdapter().fetch(limit=5) == []
    assert await PagerDutyOnCallShiftsAdapter(token="pd-token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    adapter = PagerDutyOnCallShiftsAdapter(
        token="pd-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=5) == []
