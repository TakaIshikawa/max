"""Tests for Help Scout conversation import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.helpscout_adapter import HelpScoutAdapter


@pytest.mark.asyncio
async def test_helpscout_fetch_paginates_and_maps_conversations() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["page"] == "1":
            return httpx.Response(
                200,
                json={
                    "_embedded": {
                        "conversations": [
                            {
                                "id": 1,
                                "number": 1001,
                                "subject": "Export is broken",
                                "preview": "CSV exports fail for support admins",
                                "status": "active",
                                "type": "email",
                                "mailbox": {"id": 22, "name": "Support"},
                                "primaryCustomer": {
                                    "id": 33,
                                    "first": "Rhea",
                                    "last": "Park",
                                    "email": "rhea@example.com",
                                },
                                "assignee": {"id": 44, "name": "Ada"},
                                "tags": [{"tag": "export"}],
                                "createdAt": "2026-05-01T00:00:00Z",
                                "modifiedAt": "2026-05-02T00:00:00Z",
                                "webUrl": "https://secure.helpscout.net/conversation/1",
                            }
                        ]
                    },
                    "page": {"number": 1, "totalPages": 2},
                },
            )
        return httpx.Response(
            200,
            json={
                "_embedded": {
                    "conversations": [
                        {
                            "id": 2,
                            "subject": "Billing question",
                            "status": "pending",
                            "type": "chat",
                        }
                    ]
                },
                "page": {"number": 2, "totalPages": 2},
            },
        )

    adapter = HelpScoutAdapter(
        token="hs_token",
        api_url="https://helpscout.example.test/v2",
        config={"mailbox": "22", "status": "active", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await adapter.fetch(limit=2)

    assert requests[0].headers["Authorization"] == "Bearer hs_token"
    assert requests[0].url.path == "/v2/conversations"
    assert requests[0].url.params["mailbox"] == "22"
    assert requests[0].url.params["status"] == "active"
    assert [signal.metadata["helpscout_conversation_id"] for signal in signals] == [1, 2]
    assert signals[0].title == "Export is broken"
    assert signals[0].content == "CSV exports fail for support admins"
    assert signals[0].metadata["mailbox"] == {"id": 22, "name": "Support"}
    assert signals[0].metadata["customer"]["email"] == "rhea@example.com"
    assert signals[0].metadata["assignee"]["name"] == "Ada"
    assert signals[0].metadata["tags"] == ["export"]
    assert "helpscout" in signals[0].tags


@pytest.mark.asyncio
async def test_helpscout_limit_trims_without_extra_page() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "conversations": [{"id": 1, "subject": "One"}, {"id": 2, "subject": "Two"}],
                "page": {"totalPages": 5},
            },
        )

    adapter = HelpScoutAdapter(
        token="token", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["One"]
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_helpscout_missing_credentials_and_http_error_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HELPSCOUT_API_TOKEN", raising=False)
    assert await HelpScoutAdapter().fetch() == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    adapter = HelpScoutAdapter(
        token="bad", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert await adapter.fetch() == []


def test_helpscout_resolves_token_from_config_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert HelpScoutAdapter(config={"token": "config_token"}).token == "config_token"
    monkeypatch.setenv("HELPSCOUT_API_TOKEN", "env_token")
    assert HelpScoutAdapter().token == "env_token"
