"""Tests for Opsgenie schedules import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.opsgenie_schedules_adapter import OpsgenieSchedulesImportAdapter


def _schedule(schedule_id: str = "SCHED1") -> dict:
    return {
        "id": schedule_id,
        "name": "Primary On-call",
        "apiIdentifier": "primary-on-call",
        "description": "Main production ownership schedule",
        "timezone": "America/New_York",
        "enabled": True,
        "ownerTeam": {"id": "TEAM1", "name": "Platform"},
        "rotations": [
            {
                "id": "ROT1",
                "name": "Weekday",
                "type": "weekly",
                "startDate": "2026-05-01T09:00:00Z",
                "participants": [
                    {"id": "USER1", "name": "Ada", "type": "user"},
                    {"id": "USER2", "username": "grace@example.com", "type": "user"},
                ],
            }
        ],
        "webUrl": "https://app.opsgenie.test/schedule/SCHED1",
        "createdAt": "2026-05-01T10:00:00Z",
    }


@pytest.mark.asyncio
async def test_fetches_schedules_with_auth_and_maps_schedule_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_schedule()], "paging": {}})

    adapter = OpsgenieSchedulesImportAdapter(
        api_key="ops-key",
        api_url="https://api.opsgenie.test",
        config={"page_size": 25, "offset": 10, "expand": ["rotation"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert requests[0].url.path == "/v2/schedules"
    assert requests[0].url.params["limit"] == "10"
    assert requests[0].url.params["offset"] == "10"
    assert requests[0].url.params["expand"] == "rotation"
    assert requests[0].headers["Authorization"] == "GenieKey ops-key"

    signal = signals[0]
    assert signal.id == "opsgenie-schedule:SCHED1"
    assert signal.source_adapter == "opsgenie_schedules_import"
    assert signal.title == "Opsgenie schedule Primary On-call"
    assert signal.url == "https://app.opsgenie.test/schedule/SCHED1"
    assert signal.author == "Platform"
    assert "enabled" in signal.content
    assert "timezone America/New_York" in signal.content
    assert "owner team Platform" in signal.content
    assert "Weekday weekly 2 participants" in signal.content
    assert signal.metadata["opsgenie_schedule_id"] == "SCHED1"
    assert signal.metadata["api_identifier"] == "primary-on-call"
    assert signal.metadata["timezone"] == "America/New_York"
    assert signal.metadata["enabled"] is True
    assert signal.metadata["owner_team"] == {"id": "TEAM1", "name": "Platform"}
    assert signal.metadata["rotations"][0]["participants"][1]["name"] == "grace@example.com"
    assert signal.metadata["raw"]["id"] == "SCHED1"


@pytest.mark.asyncio
async def test_fetches_paginated_schedules_and_respects_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"data": [_schedule("SCHED1")], "offset": 0, "limit": 1, "more": True},
            )
        return httpx.Response(
            200,
            json={"data": [_schedule("SCHED2")], "offset": 1, "limit": 1, "more": False},
        )

    adapter = OpsgenieSchedulesImportAdapter(
        api_key="ops-key",
        config={"page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["offset"] for request in requests] == ["0", "1"]
    assert [signal.metadata["opsgenie_schedule_id"] for signal in signals] == ["SCHED1", "SCHED2"]
    assert [signal.metadata["offset"] for signal in signals] == [0, 1]


@pytest.mark.asyncio
async def test_empty_schedules_missing_auth_bad_limit_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPSGENIE_API_KEY", raising=False)
    assert await OpsgenieSchedulesImportAdapter().fetch() == []
    assert await OpsgenieSchedulesImportAdapter(api_key="key").fetch(limit=0) == []

    empty = OpsgenieSchedulesImportAdapter(
        api_key="key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))),
    )
    assert await empty.fetch(limit=10) == []

    failing = OpsgenieSchedulesImportAdapter(
        api_key="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )
    assert await failing.fetch(limit=10) == []


@pytest.mark.asyncio
async def test_sparse_optional_fields_still_produce_readable_deterministic_signal() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"schedules": [{"name": "Backup", "isEnabled": "false", "timeZone": "UTC"}]},
        )

    adapter = OpsgenieSchedulesImportAdapter(
        api_key="ops-key",
        api_url="api.opsgenie.test/v2/schedules",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert signals[0].id == "opsgenie-schedule:Backup"
    assert signals[0].content == "Opsgenie schedule Backup; disabled; timezone UTC"
    assert signals[0].metadata["opsgenie_schedule_id"] is None
    assert signals[0].metadata["enabled"] is False
    assert signals[0].metadata["owner_team"] == {}
