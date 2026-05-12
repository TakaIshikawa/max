from __future__ import annotations

import httpx
import pytest

from max.imports.zendesk_articles_adapter import ZendeskHelpCenterArticlesAdapter


def _article(article_id: int = 101) -> dict:
    return {
        "id": article_id,
        "title": "Import Help Center articles",
        "body": "<p>Use published articles as knowledge signals.</p>",
        "html_url": f"https://help.example/hc/en-us/articles/{article_id}",
        "author_id": 42,
        "section_id": 7,
        "category_id": 3,
        "locale": "en-us",
        "label_names": ["import", "docs"],
        "draft": False,
        "archived": False,
        "promoted": True,
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-02T10:00:00Z",
    }


@pytest.mark.asyncio
async def test_fetches_zendesk_articles_with_pagination_filters_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"articles": [_article(101)], "next_page": "https://zendesk.example/api/v2/help_center/en-us/articles.json?page=2"})
        return httpx.Response(200, json={"articles": [_article(102)], "next_page": None})

    adapter = ZendeskHelpCenterArticlesAdapter(
        base_url="https://zendesk.example",
        email="agent@example.com",
        token="zendesk-token",
        config={"locale": "en-us", "section_id": "7", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/v2/help_center/en-us/sections/7/articles.json"
    assert requests[0].url.params["per_page"] == "1"
    assert signals[0].id == "zendesk-article:101"
    assert signals[0].source_adapter == "zendesk_help_center_articles_import"
    assert signals[0].title == "Import Help Center articles"
    assert signals[0].author == "42"
    assert signals[0].metadata["labels"] == ["import", "docs"]
    assert signals[0].metadata["draft"] is False
    assert signals[0].metadata["archived"] is False
    assert signals[0].metadata["raw"]["id"] == 101


@pytest.mark.asyncio
async def test_zendesk_articles_empty_without_base_url_or_on_http_error() -> None:
    assert await ZendeskHelpCenterArticlesAdapter().fetch() == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = ZendeskHelpCenterArticlesAdapter(
        base_url="https://zendesk.example",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []
