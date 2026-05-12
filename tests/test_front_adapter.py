"""Tests for Front conversation import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.front_adapter import FrontAdapter


@pytest.mark.asyncio
async def test_front_fetch_filters_paginates_and_maps_conversations() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "_results": [
                        {
                            "id": "cnv_1",
                            "subject": "Need export audit trail",
                            "latest_message": "Customers need audit context",
                            "status": "open",
                            "recipients": [{"name": "Rhea", "handle": "rhea@example.com"}],
                            "assignee": {"id": "tea_1", "name": "Ada", "email": "ada@example.com"},
                            "inboxes": [{"id": "inb_1", "name": "Support"}],
                            "tags": [{"name": "enterprise"}],
                            "created_at": 1777593600,
                            "updated_at": 1777680000,
                            "_links": {"self": "https://front.test/cnv_1"},
                        }
                    ],
                    "_pagination": {
                        "next": "https://front.example.test/conversations?page_token=next"
                    },
                },
            )
        return httpx.Response(
            200, json={"_results": [{"id": "cnv_2", "subject": "Second", "status": "archived"}]}
        )

    adapter = FrontAdapter(
        token="front_token",
        api_url="https://front.example.test",
        config={"inbox_id": "inb_1", "channel_id": "cha_1", "status": "open", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await adapter.fetch(limit=2)

    assert requests[0].headers["Authorization"] == "Bearer front_token"
    assert requests[0].url.path == "/inboxes/inb_1/conversations"
    assert requests[0].url.params["channel_id"] == "cha_1"
    assert requests[0].url.params["q[statuses]"] == "open"
    assert [signal.metadata["front_conversation_id"] for signal in signals] == ["cnv_1", "cnv_2"]
    assert signals[0].title == "Need export audit trail"
    assert signals[0].metadata["recipient"]["handle"] == "rhea@example.com"
    assert signals[0].metadata["assignee"]["name"] == "Ada"
    assert signals[0].metadata["inboxes"] == [{"id": "inb_1", "name": "Support", "email": None}]
    assert "front" in signals[0].tags


@pytest.mark.asyncio
async def test_front_missing_token_limit_and_error_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FRONT_API_TOKEN", raising=False)
    assert await FrontAdapter().fetch() == []
    assert await FrontAdapter(token="token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    adapter = FrontAdapter(
        token="bad", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert await adapter.fetch() == []


def test_front_resolves_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONT_API_TOKEN", "env_token")
    assert FrontAdapter().token == "env_token"
