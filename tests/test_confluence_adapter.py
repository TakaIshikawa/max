"""Tests for Confluence page import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.confluence_adapter import ConfluenceAdapter


@pytest.mark.asyncio
async def test_confluence_fetches_cql_results_and_maps_page() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "987",
                        "title": "Import design notes",
                        "body": {"storage": {"value": "<p>Readable <strong>storage</strong> body</p>"}},
                        "_links": {"webui": "/wiki/spaces/MAX/pages/987"},
                        "history": {"createdDate": "2026-05-01T00:00:00Z", "createdBy": {"displayName": "Ada"}},
                        "space": {"id": 1, "key": "MAX", "name": "Max"},
                        "metadata": {"labels": {"results": [{"name": "customer"}, {"name": "imports"}]}},
                        "version": {"number": 3, "when": "2026-05-02T00:00:00Z", "by": {"displayName": "Grace"}},
                        "ancestors": [{"id": "10", "title": "Parent"}],
                    }
                ]
            },
        )

    adapter = ConfluenceAdapter(
        base_url="https://max.atlassian.net",
        email="user@example.com",
        api_token="token",
        config={"cql": 'space = "MAX"', "limit": 5},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await adapter.fetch(limit=5)

    assert requests[0].url.path == "/wiki/rest/api/content/search"
    assert requests[0].url.params["cql"] == 'space = "MAX"'
    assert requests[0].url.params["limit"] == "5"
    assert signals[0].title == "Import design notes"
    assert signals[0].content == "Readable storage body"
    assert signals[0].url == "https://max.atlassian.net/wiki/spaces/MAX/pages/987"
    assert signals[0].author == "Grace"
    assert signals[0].metadata["confluence_page_id"] == "987"
    assert signals[0].metadata["space"]["key"] == "MAX"
    assert signals[0].metadata["labels"] == ["customer", "imports"]
    assert signals[0].metadata["version"]["number"] == 3
    assert signals[0].metadata["author"] == "Ada"
    assert signals[0].metadata["ancestors"] == [{"id": "10", "title": "Parent"}]


@pytest.mark.asyncio
async def test_confluence_fetches_space_pages_with_bearer_token_and_view_fallback() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [{"id": "1", "title": "Page", "body": {"view": {"value": "<div>View body</div>"}}}]})

    adapter = ConfluenceAdapter(base_url="https://conf.test", bearer_token="bearer", config={"space_key": "ENG"}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=2)

    assert requests[0].headers["Authorization"] == "Bearer bearer"
    assert requests[0].url.path == "/wiki/rest/api/content"
    assert requests[0].url.params["spaceKey"] == "ENG"
    assert signals[0].content == "View body"


@pytest.mark.asyncio
async def test_confluence_http_failure_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = ConfluenceAdapter(base_url="https://conf.test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch() == []
