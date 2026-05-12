"""Tests for Airtable record import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.airtable_adapter import AirtableAdapter


@pytest.mark.asyncio
async def test_airtable_fetch_paginates_and_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRTABLE_API_KEY", "air_env")
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"records": [{"id": "rec1", "createdTime": "2026-05-01T00:00:00Z", "fields": {"Title": "Record 1", "Description": "Desc", "Status": "Open", "Owner": "Ada", "Last Modified": "2026-05-02T00:00:00Z"}}], "offset": "next"})
        return httpx.Response(200, json={"records": [{"id": "rec2", "fields": {"Title": "Record 2"}}]})

    adapter = AirtableAdapter(config={"base_id": "base1", "table_name": "Tasks", "title_field": "Title", "view": "Grid"}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["airtable_record_id"] for signal in signals] == ["rec1", "rec2"]
    assert signals[0].metadata["status"] == "Open"
    assert calls == 2


@pytest.mark.asyncio
async def test_airtable_missing_config_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRTABLE_API_KEY", raising=False)
    assert await AirtableAdapter(config={"base_id": "base"}).fetch() == []
