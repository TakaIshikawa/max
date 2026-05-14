"""Tests for Opsgenie alert recipients import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.opsgenie_alert_recipients_adapter import OpsgenieAlertRecipientsImportAdapter


def _recipient(recipient_id: str = "USER1") -> dict:
    return {
        "id": recipient_id,
        "type": "user",
        "username": "ic@example.com",
        "name": "Incident Commander",
        "email": "ic@example.com",
        "status": "delivered",
        "delivery": {"method": "email", "state": "delivered"},
        "createdAt": "2026-05-01T10:00:00Z",
    }


@pytest.mark.asyncio
async def test_opsgenie_recipients_fetches_alias_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_recipient()], "paging": {}})

    adapter = OpsgenieAlertRecipientsImportAdapter(
        api_key="ops-key",
        api_url="https://api.opsgenie.test",
        identifier_type="alias",
        config={"aliases": ["alert-alias"], "per_page": 25},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert requests[0].url.path == "/v2/alerts/alert-alias/recipients"
    assert requests[0].url.params["identifierType"] == "alias"
    assert requests[0].url.params["limit"] == "10"
    assert requests[0].headers["Authorization"] == "GenieKey ops-key"
    signal = signals[0]
    assert signal.id == "opsgenie-alert-recipient:alert-alias:USER1"
    assert signal.source_adapter == "opsgenie_alert_recipients_import"
    assert signal.author == "Incident Commander"
    assert signal.metadata["alert_identifier"] == "alert-alias"
    assert signal.metadata["recipient_type"] == "user"
    assert signal.metadata["delivery"]["state"] == "delivered"


@pytest.mark.asyncio
async def test_opsgenie_recipients_paginates_and_respects_limit_across_alerts() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["offset"] == "0":
            return httpx.Response(200, json={"data": [_recipient("USER1")], "offset": 0, "limit": 1, "more": True})
        return httpx.Response(200, json={"data": [_recipient("USER2")], "offset": 1, "limit": 1, "more": False})

    adapter = OpsgenieAlertRecipientsImportAdapter(
        api_key="ops-key",
        config={"alert_ids": ["alert-1", "alert-2"], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["offset"] for request in requests] == ["0", "1"]
    assert [signal.metadata["recipient_id"] for signal in signals] == ["USER1", "USER2"]


@pytest.mark.asyncio
async def test_opsgenie_recipients_empty_without_config_auth_or_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPSGENIE_API_KEY", raising=False)
    assert await OpsgenieAlertRecipientsImportAdapter(config={"alert_ids": ["alert-1"]}).fetch() == []
    assert await OpsgenieAlertRecipientsImportAdapter(api_key="key").fetch() == []
    assert await OpsgenieAlertRecipientsImportAdapter(api_key="key", config={"alert_ids": ["alert-1"]}).fetch(limit=0) == []

    failing = OpsgenieAlertRecipientsImportAdapter(
        api_key="bad",
        config={"alert_ids": ["alert-1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )
    assert await failing.fetch(limit=10) == []
