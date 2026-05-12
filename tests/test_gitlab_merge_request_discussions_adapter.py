"""Tests for GitLab merge request discussions import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_merge_request_discussions_adapter import (
    GitLabMergeRequestDiscussionsAdapter,
)


def _discussion(note_id: int = 501, *, body: str = "Please update the migration.") -> dict:
    return {
        "id": "DISC1",
        "individual_note": False,
        "notes": [
            {
                "id": note_id,
                "body": body,
                "author": {
                    "id": 101,
                    "username": "reviewer",
                    "name": "Reviewer One",
                    "web_url": "https://gitlab.example/reviewer",
                },
                "created_at": "2026-05-01T10:00:00Z",
                "updated_at": "2026-05-01T10:05:00Z",
                "system": False,
                "resolvable": True,
                "resolved": False,
                "noteable_id": 7001,
                "noteable_type": "MergeRequest",
                "url": "https://gitlab.example/group/tool/-/merge_requests/17#note_501",
            }
        ],
    }


@pytest.mark.asyncio
async def test_gitlab_merge_request_discussions_fetches_flattens_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_discussion()], headers={"X-Next-Page": ""})

    adapter = GitLabMergeRequestDiscussionsAdapter(
        token="gitlab-token",
        gitlab_url="https://gitlab.example",
        config={"merge_requests": [{"project_path": "group/tool", "iid": 17}], "per_page": 5},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 1
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[0].headers["User-Agent"] == "max-gitlab-merge-request-discussions-import/1"
    assert str(requests[0].url) == (
        "https://gitlab.example/api/v4/projects/group%2Ftool/merge_requests/17/discussions?page=1&per_page=5"
    )
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "gitlab-mr-discussion-note:group/tool:17:DISC1:501"
    assert signal.source_adapter == "gitlab_merge_request_discussions_import"
    assert signal.title == "group/tool !17 discussion note"
    assert signal.content == "Please update the migration."
    assert signal.url == "https://gitlab.example/group/tool/-/merge_requests/17#note_501"
    assert signal.author == "reviewer"
    assert signal.metadata["project_id"] == "group/tool"
    assert signal.metadata["merge_request_iid"] == "17"
    assert signal.metadata["discussion_id"] == "DISC1"
    assert signal.metadata["note_id"] == 501
    assert signal.metadata["author"]["username"] == "reviewer"
    assert "discussion" in signal.tags


@pytest.mark.asyncio
async def test_gitlab_merge_request_discussions_uses_project_id_iid_and_paginates_headers() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_discussion(501)], headers={"X-Next-Page": "2"})
        return httpx.Response(200, json=[_discussion(502, body="Second page")], headers={"X-Next-Page": ""})

    adapter = GitLabMergeRequestDiscussionsAdapter(
        token="gitlab-token",
        api_url="https://gitlab.example/api/v4/",
        config={"project_id": 278964, "merge_request_iids": [17], "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert requests[0].url.path == "/api/v4/projects/278964/merge_requests/17/discussions"
    assert [signal.metadata["note_id"] for signal in signals] == [501, 502]


@pytest.mark.asyncio
async def test_gitlab_merge_request_discussions_stops_at_limit_across_merge_requests() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_discussion(501), _discussion(502)])

    adapter = GitLabMergeRequestDiscussionsAdapter(
        token="gitlab-token",
        config={"project_path": "group/tool", "merge_request_iids": [17, 18]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_gitlab_merge_request_discussions_empty_without_config_or_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabMergeRequestDiscussionsAdapter(config={"project_id": 1, "merge_request_iids": [2]}).fetch() == []
    assert await GitLabMergeRequestDiscussionsAdapter(token="token", config={"project_id": 1}).fetch() == []
    assert await GitLabMergeRequestDiscussionsAdapter(token="token", config={"project_id": 1, "merge_request_iids": [2]}).fetch(limit=0) == []

    failing = GitLabMergeRequestDiscussionsAdapter(
        token="token",
        config={"project_id": 1, "merge_request_iids": [2]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
