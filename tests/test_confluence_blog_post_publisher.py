from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.confluence_blog_posts import ConfluenceBlogPostPublishError, ConfluenceBlogPostPublisher


def test_builds_blog_post_storage_payload_with_labels() -> None:
    publisher = ConfluenceBlogPostPublisher(site_url="https://conf.example.test", space_key="MAX")

    payload = publisher.build_blog_post_payload(title="Launch note", body="<p>Hello</p>", status="draft", labels=["max", "release"])

    assert payload["type"] == "blogpost"
    assert payload["space"] == {"key": "MAX"}
    assert payload["body"]["storage"]["value"] == "<p>Hello</p>"
    assert payload["body"]["storage"]["representation"] == "storage"
    assert payload["status"] == "draft"
    assert payload["metadata"]["labels"] == ["max", "release"]


def test_from_env_reads_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_SITE_URL", "https://conf.example.test")
    monkeypatch.setenv("CONFLUENCE_SPACE_ID", "space-1")
    monkeypatch.setenv("CONFLUENCE_BEARER_TOKEN", "token")

    publisher = ConfluenceBlogPostPublisher.from_env()

    assert publisher.site_url == "https://conf.example.test"
    assert publisher.space_id == "space-1"
    assert publisher.bearer_token == "token"


def test_live_publish_posts_blogpost() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "123", "_links": {"webui": "/wiki/spaces/MAX/blog/123"}})

    publisher = ConfluenceBlogPostPublisher(site_url="https://conf.example.test", space_key="MAX", bearer_token="token", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(title="Launch note", body="<p>Hello</p>", labels=["max"], dry_run=False)

    assert result.blog_post_id == "123"
    assert result.blog_post_url == "https://conf.example.test/wiki/spaces/MAX/blog/123"
    assert requests[0].headers["Authorization"] == "Bearer token"
    posted = json.loads(requests[0].read())
    assert posted["type"] == "blogpost"
    assert posted["body"]["storage"]["value"] == "<p>Hello</p>"
    assert "metadata" not in posted


def test_missing_auth_is_actionable() -> None:
    publisher = ConfluenceBlogPostPublisher(site_url="https://conf.example.test", space_key="MAX")

    with pytest.raises(ConfluenceBlogPostPublishError, match="email/api_token or bearer_token"):
        publisher.publish(title="Launch note", body="<p>Hello</p>", dry_run=False)
