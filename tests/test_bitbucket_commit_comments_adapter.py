"""Tests for Bitbucket commit comments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.bitbucket_commit_comments_adapter import (
    BitbucketCommitCommentsAdapter,
    BitbucketCommitCommentsImportAdapter,
)


COMMENT = {
    "id": 17,
    "content": {"raw": "Please simplify this branch.", "html": "<p>Please simplify this branch.</p>"},
    "user": {"display_name": "Ada", "nickname": "ada", "uuid": "{ada}"},
    "inline": {"path": "src/app.py", "to": 42},
    "links": {"html": {"href": "https://bitbucket.org/example/tool/commits/abc123#comment-17"}},
    "created_on": "2026-05-01T10:00:00+00:00",
    "updated_on": "2026-05-02T10:00:00+00:00",
}


@pytest.mark.asyncio
async def test_bitbucket_commit_comments_fetch_follows_next_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "values": [COMMENT],
                    "next": (
                        "https://api.bitbucket.test/2.0/repositories/example/tool/"
                        "commit/abc123/comments?page=2"
                    ),
                },
            )
        return httpx.Response(200, json={"values": [{**COMMENT, "id": 18}]})

    adapter = BitbucketCommitCommentsImportAdapter(
        token="bb_token",
        api_url="https://api.bitbucket.test/2.0",
        config={
            "workspace": "example",
            "repositories": ["tool"],
            "commit_hashes": ["abc123"],
            "page_size": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert BitbucketCommitCommentsAdapter is BitbucketCommitCommentsImportAdapter
    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer bb_token"
    assert requests[0].url.path == "/2.0/repositories/example/tool/commit/abc123/comments"
    assert requests[0].url.params["pagelen"] == "1"
    assert [signal.metadata["comment_id"] for signal in signals] == [17, 18]
    assert signals[0].id == "bitbucket-commit-comment:example:tool:abc123:17"
    assert signals[0].source_adapter == "bitbucket_commit_comments_import"
    assert signals[0].source_type.value == "roadmap"
    assert signals[0].title == "Bitbucket commit abc123 comment"
    assert signals[0].content == "Please simplify this branch."
    assert signals[0].author == "Ada"
    assert signals[0].metadata["workspace"] == "example"
    assert signals[0].metadata["repository"] == "tool"
    assert signals[0].metadata["commit_hash"] == "abc123"
    assert signals[0].metadata["inline"] == {"path": "src/app.py", "to": 42}


@pytest.mark.asyncio
async def test_bitbucket_commit_comments_uses_basic_auth_and_target_tuples() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"values": [COMMENT]})

    adapter = BitbucketCommitCommentsImportAdapter(
        config={
            "username": "bot",
            "app_password": "app-password",
            "targets": [
                {"workspace": "example", "repo": "tool", "commit": "abc123"},
                {"workspace": "example", "repo": "api", "commit": "def456"},
            ],
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert requests[0].url.path == "/2.0/repositories/example/tool/commit/abc123/comments"
    assert requests[1].url.path == "/2.0/repositories/example/api/commit/def456/comments"
    assert [signal.metadata["repository"] for signal in signals] == ["tool", "api"]


@pytest.mark.asyncio
async def test_bitbucket_commit_comments_supports_env_token_and_total_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BITBUCKET_BEARER_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"values": [COMMENT, {**COMMENT, "id": 18}]})

    adapter = BitbucketCommitCommentsImportAdapter(
        config={"workspace": "example", "repository": "tool", "commit_hash": "abc123"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert requests[0].url.params["pagelen"] == "1"
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_bitbucket_commit_comments_empty_without_auth_config_or_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_BEARER_TOKEN", raising=False)

    assert (
        await BitbucketCommitCommentsImportAdapter(
            config={"workspace": "example", "repository": "tool", "commit_hash": "abc123"}
        ).fetch()
        == []
    )
    assert await BitbucketCommitCommentsImportAdapter(token="token", config={"workspace": "example"}).fetch() == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = BitbucketCommitCommentsImportAdapter(
        token="bad",
        config={"workspace": "example", "repository": "tool", "commit_hash": "abc123"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []
