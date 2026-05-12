from __future__ import annotations

import json

import httpx
import pytest

from max.imports.linear_comments_adapter import LinearCommentsAdapter


def _comment(comment_id: str = "comment-1") -> dict:
    return {
        "id": comment_id,
        "body": "This customer thread should inform delivery.",
        "url": f"https://linear.app/max/comment/{comment_id}",
        "createdAt": "2026-05-01T10:00:00.000Z",
        "updatedAt": "2026-05-02T10:00:00.000Z",
        "user": {"id": "user-1", "name": "Ada", "displayName": "Ada Lovelace", "email": "ada@example.com", "url": "https://linear.app/user/ada"},
        "issue": {
            "id": "issue-1",
            "identifier": "MAX-1",
            "title": "Ship Linear comments import",
            "url": "https://linear.app/max/issue/MAX-1/comments",
            "team": {"id": "team-1", "key": "MAX", "name": "Max"},
        },
    }


def _page(nodes: list[dict], *, cursor: str | None = None, has_next: bool = False) -> dict:
    return {"data": {"comments": {"nodes": nodes, "pageInfo": {"endCursor": cursor, "hasNextPage": has_next}}}}


@pytest.mark.asyncio
async def test_fetch_queries_graphql_comments_with_cursor_pagination_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=_page([_comment("comment-1")], cursor="cursor-1", has_next=True))
        return httpx.Response(200, json=_page([_comment("comment-2")]))

    adapter = LinearCommentsAdapter(
        token="lin-token",
        config={"page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "lin-token"
    first = json.loads(requests[0].read())
    second = json.loads(requests[1].read())
    assert "comments" in first["query"]
    assert first["variables"]["first"] == 1
    assert first["variables"]["after"] is None
    assert second["variables"]["after"] == "cursor-1"
    assert [signal.id for signal in signals] == ["linear-comment:comment-1", "linear-comment:comment-2"]
    assert signals[0].title == "MAX-1 comment"
    assert signals[0].content == "This customer thread should inform delivery."
    assert signals[0].author == "Ada Lovelace"
    assert signals[0].metadata["linear_comment_id"] == "comment-1"
    assert signals[0].metadata["issue_identifier"] == "MAX-1"
    assert signals[0].metadata["team_key"] == "MAX"
    assert signals[0].metadata["raw"]["id"] == "comment-1"


@pytest.mark.asyncio
async def test_fetch_sends_optional_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_page([]))

    adapter = LinearCommentsAdapter(
        token="lin-token",
        config={"issue_id": "issue-1", "team_id": "team-1", "updated_since": "2026-05-01T00:00:00Z"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=5) == []
    filters = json.loads(requests[0].read())["variables"]["filter"]["and"]
    assert {"issue": {"id": {"eq": "issue-1"}}} in filters
    assert {"issue": {"team": {"id": {"eq": "team-1"}}}} in filters
    assert {"updatedAt": {"gte": "2026-05-01T00:00:00Z"}} in filters


@pytest.mark.asyncio
async def test_malformed_graphql_responses_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    assert await LinearCommentsAdapter().fetch(limit=10) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "bad query"}]})

    adapter = LinearCommentsAdapter(token="lin-token", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=10) == []
