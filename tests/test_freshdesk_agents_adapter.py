"""Tests for Freshdesk agents import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.freshdesk_agents_adapter import FreshdeskAgentsAdapter


AGENT = {
    "id": 101,
    "contact": {"id": 501, "name": "Ada Lovelace", "email": "ada@example.com"},
    "active": True,
    "available": False,
    "ticket_scope": 2,
    "group_ids": [10, 20],
    "role_ids": [30],
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-02T11:00:00Z",
}


@pytest.mark.asyncio
async def test_freshdesk_agents_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("page") == "1":
            return httpx.Response(
                200,
                json=[AGENT],
                headers={"Link": '<https://acme.freshdesk.com/api/v2/agents?page=2&per_page=1>; rel="next"'},
            )
        return httpx.Response(200, json=[{**AGENT, "id": 102, "contact": {"name": "Grace Hopper", "email": "grace@example.com"}}])

    adapter = FreshdeskAgentsAdapter(
        domain="acme",
        api_key="fd-key",
        config={"page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/v2/agents"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].headers["Authorization"] == f"Basic {base64.b64encode(b'fd-key:X').decode()}"
    assert requests[0].headers["User-Agent"] == "max-freshdesk-agents-import/1"
    assert requests[1].url.params["page"] == "2"

    signal = signals[0]
    assert signal.id == "freshdesk-agent:101"
    assert signal.source_adapter == "freshdesk_agents_import"
    assert signal.title == "Ada Lovelace"
    assert signal.content == "Freshdesk agent; Ada Lovelace; ada@example.com; active True; available False; ticket scope 2"
    assert signal.url == "https://acme.freshdesk.com/a/admin/agents/101"
    assert signal.author == "ada@example.com"
    assert signal.metadata["agent_id"] == 101
    assert signal.metadata["contact_id"] == 501
    assert signal.metadata["name"] == "Ada Lovelace"
    assert signal.metadata["email"] == "ada@example.com"
    assert signal.metadata["active"] is True
    assert signal.metadata["available"] is False
    assert signal.metadata["ticket_scope"] == 2
    assert signal.metadata["group_ids"] == [10, 20]
    assert signal.metadata["role_ids"] == [30]
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-02T11:00:00Z"
    assert signal.metadata["raw"] == AGENT


@pytest.mark.asyncio
async def test_freshdesk_agents_respects_limit_and_page_size() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[AGENT, {**AGENT, "id": 102}])

    adapter = FreshdeskAgentsAdapter(
        domain="https://help.example.com/",
        api_key="fd-key",
        config={"per_page": 100},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].url.host == "help.example.com"
    assert requests[0].url.params["per_page"] == "1"
    assert [signal.id for signal in signals] == ["freshdesk-agent:101"]


@pytest.mark.asyncio
async def test_freshdesk_agents_empty_without_required_config_or_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRESHDESK_DOMAIN", raising=False)
    monkeypatch.delenv("FRESHDESK_API_KEY", raising=False)

    assert await FreshdeskAgentsAdapter(domain="acme").fetch() == []
    assert await FreshdeskAgentsAdapter(api_key="key").fetch() == []
    assert await FreshdeskAgentsAdapter(domain="acme", api_key="key").fetch(limit=0) == []

    failing = FreshdeskAgentsAdapter(
        domain="acme",
        api_key="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
