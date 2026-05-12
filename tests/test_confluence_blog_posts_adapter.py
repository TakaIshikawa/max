from __future__ import annotations

import httpx
import pytest

from max.imports.confluence_blog_posts_adapter import ConfluenceBlogPostsAdapter, ConfluenceBlogPostsImportAdapter


@pytest.mark.asyncio
async def test_fetches_blog_posts_with_filters_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_post()]})

    adapter = ConfluenceBlogPostsImportAdapter(
        base_url="https://max.atlassian.net",
        email="user@example.com",
        api_token="token",
        space_keys=["ENG", "PM"],
        label="release",
        status="current",
        per_page=10,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert ConfluenceBlogPostsAdapter is ConfluenceBlogPostsImportAdapter
    assert requests[0].url.path == "/wiki/rest/api/content"
    assert requests[0].url.params["type"] == "blogpost"
    assert requests[0].url.params["spaceKey"] == "ENG,PM"
    assert requests[0].url.params["label"] == "release"
    assert requests[0].url.params["status"] == "current"
    assert requests[0].url.params["limit"] == "5"
    assert signals[0].title == "Release notes"
    assert signals[0].content == "Shipped import adapters"
    assert signals[0].url == "https://max.atlassian.net/wiki/spaces/ENG/blog/123"
    assert signals[0].metadata["confluence_blog_post_id"] == "123"
    assert signals[0].metadata["labels"] == ["release"]
    assert "blogpost" in signals[0].tags


@pytest.mark.asyncio
async def test_supports_bearer_cloud_mode_and_pagination() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"results": [_post("1"), _post("2")]})
        return httpx.Response(200, json={"results": [_post("3")]})

    adapter = ConfluenceBlogPostsImportAdapter(
        cloud_id="cloud-1",
        bearer_token="bearer",
        per_page=2,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert len(signals) == 3
    assert requests[0].url.host == "api.atlassian.com"
    assert requests[0].headers["Authorization"] == "Bearer bearer"
    assert requests[1].url.params["start"] == "2"
    assert requests[1].url.params["limit"] == "1"


@pytest.mark.asyncio
async def test_missing_credentials_non_positive_limit_and_errors_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONFLUENCE_EMAIL", raising=False)
    monkeypatch.delenv("CONFLUENCE_API_TOKEN", raising=False)
    monkeypatch.delenv("CONFLUENCE_BEARER_TOKEN", raising=False)
    assert await ConfluenceBlogPostsImportAdapter(base_url="https://conf.test").fetch(limit=5) == []
    assert await ConfluenceBlogPostsImportAdapter(base_url="https://conf.test", bearer_token="token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = ConfluenceBlogPostsImportAdapter(base_url="https://conf.test", bearer_token="token", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=1) == []


def _post(suffix: str = "") -> dict:
    return {
        "id": f"123{suffix}",
        "title": "Release notes",
        "status": "current",
        "body": {"storage": {"value": "<p>Shipped <strong>import</strong> adapters</p>"}},
        "_links": {"webui": "/wiki/spaces/ENG/blog/123"},
        "history": {"createdDate": "2026-05-01T00:00:00Z", "createdBy": {"displayName": "Ada"}},
        "version": {"number": 2, "when": "2026-05-02T00:00:00Z", "by": {"displayName": "Grace"}},
        "space": {"id": "10", "key": "ENG", "name": "Engineering"},
        "metadata": {"labels": {"results": [{"name": "release"}]}},
    }
