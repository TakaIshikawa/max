from __future__ import annotations

import httpx
import pytest

from max.imports.pagerduty_incident_notes_adapter import PagerDutyIncidentNotesAdapter


def _note(note_id: str = "PNOTE1", *, user: dict | None = None) -> dict:
    return {
        "id": note_id,
        "content": "Restarted the worker pool.",
        "created_at": "2026-05-01T10:00:00Z",
        "user": user
        if user is not None
        else {
            "id": "PUSER1",
            "summary": "Incident Commander",
            "email": "ic@example.com",
            "html_url": "https://acme.pagerduty.com/users/PUSER1",
        },
    }


@pytest.mark.asyncio
async def test_fetches_incident_notes_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"notes": [_note()], "more": False})

    adapter = PagerDutyIncidentNotesAdapter(
        api_token="pd-token",
        from_email="max@example.com",
        api_url="https://api.pagerduty.test",
        config={"incident_ids": ["PINC1"], "web_url": "https://acme.pagerduty.com"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert requests[0].url.path == "/incidents/PINC1/notes"
    assert requests[0].headers["Authorization"] == "Token token=pd-token"
    assert requests[0].headers["From"] == "max@example.com"
    signal = signals[0]
    assert signal.id == "pagerduty-note:PINC1:PNOTE1"
    assert signal.source_type.value == "failure_data"
    assert signal.content == "Restarted the worker pool."
    assert signal.author == "Incident Commander"
    assert signal.url == "https://acme.pagerduty.com/incidents/PINC1"
    assert signal.metadata["pagerduty_note_id"] == "PNOTE1"
    assert signal.metadata["pagerduty_incident_id"] == "PINC1"
    assert signal.metadata["author"]["email"] == "ic@example.com"


@pytest.mark.asyncio
async def test_empty_response_returns_no_signals() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"notes": [], "more": False})

    adapter = PagerDutyIncidentNotesAdapter(
        api_token="pd-token",
        config={"incident_id": "PINC1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=10) == []


@pytest.mark.asyncio
async def test_fetches_paginated_notes_without_duplicate_records() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"notes": [_note("PNOTE1")], "limit": 1, "offset": 0, "more": True})
        return httpx.Response(200, json={"notes": [_note("PNOTE1"), _note("PNOTE2")], "limit": 1, "offset": 1, "more": False})

    adapter = PagerDutyIncidentNotesAdapter(
        api_token="pd-token",
        config={"incident_ids": "PINC1", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert [request.url.params["offset"] for request in requests] == ["0", "1"]
    assert [signal.id for signal in signals] == [
        "pagerduty-note:PINC1:PNOTE1",
        "pagerduty-note:PINC1:PNOTE2",
    ]


@pytest.mark.asyncio
async def test_discovers_incidents_from_query_params_before_fetching_notes() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/incidents":
            return httpx.Response(200, json={"incidents": [{"id": "PINC2"}], "more": False})
        return httpx.Response(200, json={"notes": [_note("PNOTE2")], "more": False})

    adapter = PagerDutyIncidentNotesAdapter(
        api_token="pd-token",
        api_url="https://api.pagerduty.test",
        config={"query_params": {"statuses[]": "triggered", "team_ids[]": "PTEAM1"}},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requests[0].url.path == "/incidents"
    assert requests[0].url.params["statuses[]"] == "triggered"
    assert requests[1].url.path == "/incidents/PINC2/notes"
    assert signals[0].metadata["pagerduty_incident_id"] == "PINC2"


@pytest.mark.asyncio
async def test_missing_optional_author_fields_are_handled() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"notes": [_note("PNOTE3", user={"id": "PUSER3"})], "more": False})

    adapter = PagerDutyIncidentNotesAdapter(
        api_token="pd-token",
        config={"incident_id": "PINC3"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert signals[0].author == "PUSER3"
    assert signals[0].metadata["author"]["id"] == "PUSER3"
    assert signals[0].metadata["author"]["email"] is None
