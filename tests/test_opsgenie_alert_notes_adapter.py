"""Tests for Opsgenie alert notes import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.opsgenie_alert_notes_adapter import OpsgenieAlertNotesImportAdapter


def _note(note_id: str = "NOTE1", *, owner: object | None = None) -> dict:
    return {
        "id": note_id,
        "note": "Deployment verified by on-call.",
        "owner": owner
        if owner is not None
        else {
            "id": "USER1",
            "username": "ic@example.com",
            "name": "Incident Commander",
            "email": "ic@example.com",
        },
        "createdAt": "2026-05-01T10:00:00Z",
        "source": "web",
    }


@pytest.mark.asyncio
async def test_fetches_alert_notes_with_identifier_type_order_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_note()], "paging": {}})

    adapter = OpsgenieAlertNotesImportAdapter(
        api_key="ops-key",
        api_url="https://api.opsgenie.test",
        config={
            "identifier": "alert-alias",
            "identifier_type": "alias",
            "order": "desc",
            "page_size": 25,
            "offset": 10,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert requests[0].url.path == "/v2/alerts/alert-alias/notes"
    assert requests[0].url.params["identifierType"] == "alias"
    assert requests[0].url.params["order"] == "desc"
    assert requests[0].url.params["limit"] == "10"
    assert requests[0].url.params["offset"] == "10"
    assert requests[0].headers["Authorization"] == "GenieKey ops-key"

    signal = signals[0]
    assert signal.id == "opsgenie-alert-note:alert-alias:NOTE1"
    assert signal.source_adapter == "opsgenie_alert_notes_import"
    assert signal.source_type.value == "failure_data"
    assert signal.content == "Deployment verified by on-call."
    assert signal.author == "ic@example.com"
    assert signal.metadata["opsgenie_note_id"] == "NOTE1"
    assert signal.metadata["alert_identifier"] == "alert-alias"
    assert signal.metadata["identifier_type"] == "alias"
    assert signal.metadata["note"] == "Deployment verified by on-call."
    assert signal.metadata["owner"]["email"] == "ic@example.com"
    assert signal.metadata["createdAt"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["source"] == "web"
    assert signal.metadata["offset"] == 10
    assert signal.metadata["source_adapter"] == "opsgenie_alert_notes_import"


@pytest.mark.asyncio
async def test_fetches_paginated_alert_notes_and_respects_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"data": [_note("NOTE1")], "offset": 0, "limit": 1, "more": True},
            )
        return httpx.Response(
            200,
            json={"data": [_note("NOTE2")], "offset": 1, "limit": 1, "more": True},
        )

    adapter = OpsgenieAlertNotesImportAdapter(
        api_key="ops-key",
        config={"alert_id": "alert-123", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["offset"] for request in requests] == ["0", "1"]
    assert [signal.metadata["opsgenie_note_id"] for signal in signals] == ["NOTE1", "NOTE2"]
    assert [signal.metadata["offset"] for signal in signals] == [0, 1]


@pytest.mark.asyncio
async def test_supports_env_api_key_and_normalizes_api_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPSGENIE_API_KEY", "env-key")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_note(owner="ops@example.com")]})

    adapter = OpsgenieAlertNotesImportAdapter(
        api_url="api.eu.opsgenie.test/v2/alerts",
        alert_id="alert-123",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert str(requests[0].url).startswith("https://api.eu.opsgenie.test/v2/alerts/alert-123/notes")
    assert requests[0].headers["Authorization"] == "GenieKey env-key"
    assert signals[0].author == "ops@example.com"
    assert signals[0].metadata["owner"] == {"name": "ops@example.com"}


@pytest.mark.asyncio
async def test_empty_for_missing_config_bad_limits_failures_and_malformed_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPSGENIE_API_KEY", raising=False)
    assert await OpsgenieAlertNotesImportAdapter(config={"alert_id": "alert-123"}).fetch() == []
    assert await OpsgenieAlertNotesImportAdapter(api_key="key").fetch() == []
    assert await OpsgenieAlertNotesImportAdapter(api_key="key", config={"alert_id": "alert-123"}).fetch(limit=0) == []

    async def failure_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    failing = OpsgenieAlertNotesImportAdapter(
        api_key="bad",
        config={"alert_id": "alert-123"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(failure_handler)),
    )
    assert await failing.fetch(limit=10) == []

    async def malformed_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"note": "missing id"}, "bad"]})

    malformed = OpsgenieAlertNotesImportAdapter(
        api_key="key",
        config={"alert_id": "alert-123"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(malformed_handler)),
    )
    assert await malformed.fetch(limit=10) == []
