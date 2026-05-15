from __future__ import annotations

import httpx
import pytest

from max.imports.confluence_pages_adapter import ConfluencePagesAdapter, ConfluencePagesImportAdapter


@pytest.mark.asyncio
async def test_fetches_pages_from_space_and_maps_signal_metadata() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_page("100", title="Runbook")]})

    adapter = ConfluencePagesImportAdapter(
        base_url="https://max.atlassian.net",
        email="user@example.com",
        api_token="token",
        space_key="ENG",
        per_page=10,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert ConfluencePagesAdapter is ConfluencePagesImportAdapter
    assert requests[0].url.path == "/wiki/rest/api/content"
    assert requests[0].url.params["type"] == "page"
    assert requests[0].url.params["spaceKey"] == "ENG"
    assert requests[0].url.params["limit"] == "5"
    assert signals[0].id == "confluence-page:ENG:100"
    assert signals[0].title == "Runbook"
    assert signals[0].content == "Short rollout notes"
    assert signals[0].url == "https://max.atlassian.net/wiki/spaces/ENG/pages/100"
    assert signals[0].author == "Grace"
    assert signals[0].published_at is not None
    assert signals[0].metadata["confluence_page_id"] == "100"
    assert signals[0].metadata["space_key"] == "ENG"
    assert signals[0].metadata["labels"] == ["runbook", "release"]
    assert signals[0].metadata["version"]["number"] == 4
    assert signals[0].metadata["author"]["display_name"] == "Grace"
    assert signals[0].metadata["updated_date"] == "2026-05-02T00:00:00Z"
    assert signals[0].metadata["web_url"] == "https://max.atlassian.net/wiki/spaces/ENG/pages/100"
    assert "page" in signals[0].tags


@pytest.mark.asyncio
async def test_body_storage_fallback_when_excerpt_is_missing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        page = _page("101")
        page.pop("excerpt")
        return httpx.Response(200, json={"results": [page]})

    adapter = ConfluencePagesImportAdapter(
        base_url="https://conf.test",
        bearer_token="bearer",
        space_key="ENG",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert signals[0].content == "Full storage body"


@pytest.mark.asyncio
async def test_follows_confluence_next_link_pagination() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "results": [_page("1"), _page("2")],
                    "_links": {"next": "/wiki/rest/api/content?start=2&limit=2"},
                },
            )
        return httpx.Response(200, json={"results": [_page("3")]})

    adapter = ConfluencePagesImportAdapter(
        base_url="https://conf.test",
        bearer_token="bearer",
        space_key="ENG",
        per_page=2,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert [signal.metadata["confluence_page_id"] for signal in signals] == ["1", "2", "3"]
    assert requests[0].headers["Authorization"] == "Bearer bearer"
    assert requests[1].url.path == "/wiki/rest/api/content"
    assert requests[1].url.params["start"] == "2"
    assert requests[1].url.params["limit"] == "2"


@pytest.mark.asyncio
async def test_follows_cursor_pagination() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"results": [_page("1")], "nextCursor": "cursor-2"})
        return httpx.Response(200, json={"results": [_page("2")]})

    adapter = ConfluencePagesImportAdapter(
        base_url="https://conf.test",
        bearer_token="bearer",
        space_key="ENG",
        per_page=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["confluence_page_id"] for signal in signals] == ["1", "2"]
    assert requests[1].url.params["cursor"] == "cursor-2"
    assert "start" not in requests[1].url.params


@pytest.mark.asyncio
async def test_missing_configuration_non_positive_limit_and_api_failure_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CONFLUENCE_EMAIL", raising=False)
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)
    monkeypatch.delenv("CONFLUENCE_BEARER_TOKEN", raising=False)

    assert await ConfluencePagesImportAdapter(base_url="https://conf.test", space_key="ENG").fetch(limit=1) == []
    assert await ConfluencePagesImportAdapter(base_url="https://conf.test", bearer_token="token").fetch(limit=1) == []
    assert await ConfluencePagesImportAdapter(base_url="https://conf.test", bearer_token="token", space_key="ENG").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = ConfluencePagesImportAdapter(
        base_url="https://conf.test",
        bearer_token="token",
        space_key="ENG",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch(limit=1) == []


def _page(page_id: str, *, title: str = "Planning page") -> dict:
    return {
        "id": page_id,
        "title": title,
        "status": "current",
        "excerpt": "<p>Short <strong>rollout</strong> notes</p>",
        "body": {"storage": {"value": "<p>Full <strong>storage</strong> body</p>"}},
        "_links": {"webui": f"/wiki/spaces/ENG/pages/{page_id}"},
        "history": {
            "createdDate": "2026-05-01T00:00:00Z",
            "createdBy": {"accountId": "a-1", "displayName": "Ada"},
        },
        "version": {
            "number": 4,
            "when": "2026-05-02T00:00:00Z",
            "by": {"accountId": "g-1", "displayName": "Grace"},
        },
        "space": {"id": "10", "key": "ENG", "name": "Engineering"},
        "metadata": {"labels": {"results": [{"name": "runbook"}, {"name": "release"}]}},
    }
