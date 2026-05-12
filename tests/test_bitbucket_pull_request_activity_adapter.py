"""Tests for Bitbucket pull request activity import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.bitbucket_pull_request_activity_adapter import BitbucketPullRequestActivityAdapter
from max.types.signal import SignalSourceType


COMMENT_ACTIVITY = {
    "comment": {
        "id": 1001,
        "content": {"raw": "Please add a regression test.", "markup": "markdown"},
        "user": {"display_name": "Ada", "nickname": "ada", "uuid": "{user-uuid}"},
        "links": {"html": {"href": "https://bitbucket.org/example/tool/pull-requests/7/_/diff#comment-1001"}},
        "created_on": "2026-05-01T10:00:00+00:00",
        "updated_on": "2026-05-01T11:00:00+00:00",
    }
}

APPROVAL_ACTIVITY = {
    "approval": {
        "user": {"display_name": "Grace", "nickname": "grace", "uuid": "{approval-user}"},
        "date": "2026-05-01T12:00:00+00:00",
        "links": {"html": {"href": "https://bitbucket.org/example/tool/pull-requests/7"}},
    }
}

UPDATE_ACTIVITY = {
    "update": {
        "state": "MERGED",
        "title": "Ship activity import",
        "author": {"display_name": "Linus", "nickname": "linus", "uuid": "{update-user}"},
        "date": "2026-05-01T13:00:00+00:00",
        "links": {"html": {"href": "https://bitbucket.org/example/tool/pull-requests/8"}},
    }
}

OTHER_ACTIVITY = {
    "changes_requested": {
        "user": {"display_name": "Barbara", "nickname": "barbara", "uuid": "{changes-user}"},
        "date": "2026-05-01T14:00:00+00:00",
        "links": {"html": {"href": "https://bitbucket.org/example/tool/pull-requests/8"}},
    }
}


@pytest.mark.asyncio
async def test_bitbucket_pull_request_activity_fetches_follows_next_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "values": [COMMENT_ACTIVITY],
                    "next": "https://api.bitbucket.test/2.0/repositories/example/tool/pullrequests/7/activity?page=2",
                },
            )
        return httpx.Response(200, json={"values": [APPROVAL_ACTIVITY]})

    adapter = BitbucketPullRequestActivityAdapter(
        bearer_token="bb-token",
        api_url="https://api.bitbucket.test/2.0",
        config={"workspace": "example", "repo_slug": "tool", "pull_request_ids": [7], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer bb-token"
    assert requests[0].headers["User-Agent"] == "max-bitbucket-pull-request-activity-import/1"
    assert requests[0].url.path == "/2.0/repositories/example/tool/pullrequests/7/activity"
    assert requests[0].url.params["pagelen"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert "pagelen" not in requests[1].url.params
    assert [signal.metadata["activity_type"] for signal in signals] == ["comment", "approval"]

    signal = signals[0]
    assert signal.id == "bitbucket-pr-activity:example:tool:7:1001"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "bitbucket_pull_request_activity_import"
    assert signal.title == "example/tool PR #7 comment"
    assert signal.content == "Please add a regression test."
    assert signal.url.endswith("#comment-1001")
    assert signal.author == "Ada"
    assert signal.metadata["workspace"] == "example"
    assert signal.metadata["repository"] == "tool"
    assert signal.metadata["pull_request_id"] == "7"
    assert signal.metadata["actor"]["nickname"] == "ada"
    assert signal.metadata["comment"]["id"] == 1001
    assert signal.metadata["raw"] == COMMENT_ACTIVITY
    assert "activity" in signal.tags
    assert "comment" in signal.tags
    assert signals[1].content == "approved pull request"
    assert signals[1].author == "Grace"


@pytest.mark.asyncio
async def test_bitbucket_pull_request_activity_supports_pull_request_objects_basic_auth_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"values": [UPDATE_ACTIVITY, OTHER_ACTIVITY]})

    adapter = BitbucketPullRequestActivityAdapter(
        config={
            "pull_requests": [
                {"workspace": "example", "repository": "team/tool", "id": 7},
                {"workspace": "example", "repo_slug": "tool", "pull_request_id": 8},
            ],
            "username": "ada",
            "app_password": "app-pass",
            "page_size": 50,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    expected = "Basic " + base64.b64encode(b"ada:app-pass").decode()
    assert requests[0].headers["Authorization"] == expected
    assert requests[0].url.path == "/2.0/repositories/example/tool/pullrequests/7/activity"
    assert requests[0].url.params["pagelen"] == "1"
    assert len(requests) == 1
    assert len(signals) == 1
    assert signals[0].metadata["activity_type"] == "status_change"
    assert signals[0].content == "changed status to MERGED: Ship activity import"
    assert signals[0].author == "Linus"
    assert "status_change" in signals[0].tags


@pytest.mark.asyncio
async def test_bitbucket_pull_request_activity_uses_defaults_for_pull_request_objects_and_maps_other_activity() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"values": [OTHER_ACTIVITY]})

    adapter = BitbucketPullRequestActivityAdapter(
        bearer_token="token",
        config={
            "workspace": "example",
            "repo_slug": "tool",
            "pull_requests": [{"pull_request_id": 8}],
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requests[0].url.path == "/2.0/repositories/example/tool/pullrequests/8/activity"
    assert signals[0].metadata["activity_type"] == "changes_requested"
    assert signals[0].content == "requested changes"
    assert signals[0].author == "Barbara"
    assert signals[0].metadata["changes_requested"]["date"] == "2026-05-01T14:00:00+00:00"


@pytest.mark.asyncio
async def test_bitbucket_pull_request_activity_empty_without_config_auth_or_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)
    monkeypatch.delenv("BITBUCKET_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)

    assert await BitbucketPullRequestActivityAdapter(config={"workspace": "example", "repo_slug": "tool", "pull_request_ids": [7]}).fetch() == []
    assert await BitbucketPullRequestActivityAdapter(bearer_token="token", config={"workspace": "example", "repo_slug": "tool"}).fetch() == []
    assert await BitbucketPullRequestActivityAdapter(bearer_token="token", config={"workspace": "example", "repo_slug": "tool", "pull_request_ids": [7]}).fetch(limit=0) == []

    failing = BitbucketPullRequestActivityAdapter(
        bearer_token="token",
        config={"workspace": "example", "repo_slug": "tool", "pull_request_ids": [7]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []
