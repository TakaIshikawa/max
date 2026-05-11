"""Tests for Trello card import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.trello_adapter import TrelloAdapter


@pytest.mark.asyncio
async def test_trello_fetch_maps_dedupes_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRELLO_API_KEY", "key")
    monkeypatch.setenv("TRELLO_TOKEN", "token")
    requests: list[httpx.Request] = []
    card = {"id": "c1", "name": "Card", "desc": "Desc", "url": "https://trello.test/c1", "idBoard": "b1", "idList": "l1", "closed": False, "dateLastActivity": "2026-05-01T00:00:00Z", "shortLink": "abc", "labels": [{"name": "Customer"}], "members": [{"username": "ada"}]}

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[card, card])

    adapter = TrelloAdapter(config={"board_ids": ["b1"], "labels": ["Customer"]}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert adapter.board_ids == ["b1"]
    assert requests[0].url.path == "/1/boards/b1/cards"
    assert signals[0].metadata["trello_card_id"] == "c1"
    assert signals[0].metadata["labels"] == ["Customer"]


@pytest.mark.asyncio
async def test_trello_missing_credentials_and_errors_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRELLO_API_KEY", raising=False)
    monkeypatch.delenv("TRELLO_TOKEN", raising=False)
    assert await TrelloAdapter(config={"board_ids": ["b1"]}).fetch() == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = TrelloAdapter(config={"board_ids": ["b1"]}, key="key", token="token", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=5) == []
