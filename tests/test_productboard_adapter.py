"""Tests for Productboard insight import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.productboard_adapter import ProductboardAdapter


@pytest.mark.asyncio
async def test_productboard_fetch_paginates_and_maps_notes() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "note_1",
                            "title": "Admin exports",
                            "content": "Admins need cleaner CSV exports",
                            "source": "intercom",
                            "customer": {
                                "id": "cus_1",
                                "name": "Rhea",
                                "email": "rhea@example.com",
                            },
                            "company": {"id": "com_1", "name": "Acme"},
                            "tags": [{"name": "export"}],
                            "features": [{"id": "fea_1", "name": "Reporting"}],
                            "created_at": "2026-05-01T00:00:00Z",
                            "updated_at": "2026-05-02T00:00:00Z",
                            "url": "https://productboard.test/notes/note_1",
                        }
                    ],
                    "nextPageCursor": "next",
                },
            )
        return httpx.Response(200, json={"data": [{"id": "note_2", "title": "Second"}]})

    adapter = ProductboardAdapter(
        token="pb_token",
        api_url="https://productboard.example.test",
        config={"query": "exports", "status": "new", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await adapter.fetch(limit=2)

    assert requests[0].headers["Authorization"] == "Bearer pb_token"
    assert requests[0].url.path == "/notes"
    assert requests[0].url.params["query"] == "exports"
    assert requests[0].url.params["status"] == "new"
    assert requests[1].url.params["pageCursor"] == "next"
    assert [signal.metadata["productboard_insight_id"] for signal in signals] == [
        "note_1",
        "note_2",
    ]
    assert signals[0].title == "Admin exports"
    assert signals[0].metadata["customer"]["email"] == "rhea@example.com"
    assert signals[0].metadata["company"]["name"] == "Acme"
    assert signals[0].metadata["features"] == [{"id": "fea_1", "name": "Reporting", "email": None}]
    assert "productboard" in signals[0].tags


@pytest.mark.asyncio
async def test_productboard_missing_token_limit_and_error_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PRODUCTBOARD_API_TOKEN", raising=False)
    assert await ProductboardAdapter().fetch() == []
    assert await ProductboardAdapter(token="token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = ProductboardAdapter(
        token="bad", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert await adapter.fetch() == []


def test_productboard_resolves_config_and_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    assert ProductboardAdapter(config={"token": "config_token"}).token == "config_token"
    monkeypatch.setenv("PRODUCTBOARD_API_TOKEN", "env_token")
    assert ProductboardAdapter().token == "env_token"
