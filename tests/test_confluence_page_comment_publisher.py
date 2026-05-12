from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher.confluence_page_comments import ConfluencePageCommentPublishError, ConfluencePageCommentPublisher


@pytest.mark.asyncio
async def test_dry_run_builds_footer_comment_payload() -> None:
    publisher = ConfluencePageCommentPublisher("https://example.atlassian.net", page_id="12345")

    result = await publisher.publish(body="<p>Review note</p>", dry_run=True)

    assert result.endpoint == "https://example.atlassian.net/wiki/rest/api/content"
    assert result.page_id == "12345"
    assert result.comment_id is None
    assert result.payload["body"]["storage"]["value"] == "<p>Review note</p>"
    assert result.payload["body"]["storage"]["representation"] == "storage"
    assert result.payload["metadata"]["publisher"] == "max.confluence_page_comments"


@pytest.mark.asyncio
async def test_live_publish_posts_confluence_page_comment_with_basic_auth() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "comment-1", "_links": {"webui": "/wiki/spaces/MAX/pages/12345?focusedCommentId=comment-1"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = ConfluencePageCommentPublisher(
        "https://example.atlassian.net",
        page_id="12345",
        email="agent@example.com",
        api_token="api-token",
        client=client,
    )

    result = await publisher.publish(body="<p>Review note</p>", dry_run=False)
    await client.aclose()

    assert result.status_code == 200
    assert result.comment_id == "comment-1"
    assert result.comment_url == "https://example.atlassian.net/wiki/spaces/MAX/pages/12345?focusedCommentId=comment-1"
    expected_auth = base64.b64encode(b"agent@example.com:api-token").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    posted = json.loads(requests[0].read())
    assert posted["type"] == "comment"
    assert posted["container"] == {"type": "page", "id": "12345"}
    assert posted["body"]["storage"]["value"] == "<p>Review note</p>"


@pytest.mark.asyncio
async def test_atlas_doc_format_body_and_bearer_auth() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "comment-2"})

    adf = {"atlas_doc_format": {"value": {"type": "doc", "version": 1, "content": []}, "representation": "atlas_doc_format"}}
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = ConfluencePageCommentPublisher(
        "https://example.atlassian.net",
        page_id="12345",
        bearer_token="bearer-token",
        client=client,
    )

    result = await publisher.publish(body=adf, dry_run=False)
    await client.aclose()

    assert result.comment_id == "comment-2"
    assert requests[0].headers["Authorization"] == "Bearer bearer-token"
    assert json.loads(requests[0].read())["body"] == adf


def test_from_env_reads_confluence_comment_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_SITE_URL", "https://env.atlassian.net")
    monkeypatch.setenv("CONFLUENCE_PAGE_ID", "24680")
    monkeypatch.setenv("CONFLUENCE_EMAIL", "env@example.com")
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "env-token")

    publisher = ConfluencePageCommentPublisher.from_env()

    assert publisher.site_url == "https://env.atlassian.net"
    assert publisher.page_id == "24680"
    assert publisher.email == "env@example.com"
    assert publisher.api_token == "env-token"


@pytest.mark.asyncio
async def test_live_publish_requires_auth() -> None:
    publisher = ConfluencePageCommentPublisher("https://example.atlassian.net", page_id="12345")

    with pytest.raises(ConfluencePageCommentPublishError, match="required"):
        await publisher.publish(body="<p>Review note</p>", dry_run=False)
