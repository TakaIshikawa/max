"""Tests for GitLab issue discussions import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_issue_discussions_adapter import GitLabIssueDiscussionsAdapter


def _discussion(note_id: int = 501, *, body: str = "Please add customer context.") -> dict:
    return {
        "id": "DISC1",
        "individual_note": False,
        "notes": [
            {
                "id": note_id,
                "body": body,
                "author": {
                    "id": 101,
                    "username": "reporter",
                    "name": "Reporter One",
                    "web_url": "https://gitlab.example/reporter",
                },
                "created_at": "2026-05-01T10:00:00Z",
                "updated_at": "2026-05-01T10:05:00Z",
                "system": False,
                "resolvable": True,
                "resolved": False,
                "noteable_id": 7001,
                "noteable_type": "Issue",
                "url": "https://gitlab.example/group/tool/-/issues/17#note_501",
            }
        ],
    }


@pytest.mark.asyncio
async def test_gitlab_issue_discussions_fetches_flattens_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_discussion()], headers={"X-Next-Page": ""})

    adapter = GitLabIssueDiscussionsAdapter(
        token="gitlab-token",
        gitlab_url="https://gitlab.example",
        config={"issues": [{"project_path": "group/tool", "issue_iid": 17}], "per_page": 5},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 1
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[0].headers["User-Agent"] == "max-gitlab-issue-discussions-import/1"
    assert str(requests[0].url) == (
        "https://gitlab.example/api/v4/projects/group%2Ftool/issues/17/discussions?page=1&per_page=5"
    )
    signal = signals[0]
    assert signal.id == "gitlab-issue-discussion-note:group/tool:17:DISC1:501"
    assert signal.source_adapter == "gitlab_issue_discussions_import"
    assert signal.title == "group/tool issue #17 discussion note"
    assert signal.content == "Please add customer context."
    assert signal.author == "reporter"
    assert signal.metadata["project_id"] == "group/tool"
    assert signal.metadata["issue_iid"] == "17"
    assert signal.metadata["discussion_id"] == "DISC1"
    assert signal.metadata["author"]["username"] == "reporter"
    assert "resolvable" in signal.tags


@pytest.mark.asyncio
async def test_gitlab_issue_discussions_uses_project_iids_and_paginates_headers() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_discussion(501)], headers={"X-Next-Page": "2"})
        return httpx.Response(200, json=[_discussion(502, body="Second page")], headers={"X-Next-Page": ""})

    adapter = GitLabIssueDiscussionsAdapter(
        private_token="gitlab-token",
        api_url="https://gitlab.example/api/v4/",
        config={"project_id": 278964, "issue_iids": [17], "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert requests[0].url.path == "/api/v4/projects/278964/issues/17/discussions"
    assert [signal.metadata["note_id"] for signal in signals] == [501, 502]


@pytest.mark.asyncio
async def test_gitlab_issue_discussions_stops_at_limit_across_issues() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_discussion(501), _discussion(502)])

    adapter = GitLabIssueDiscussionsAdapter(
        token="gitlab-token",
        config={"project_path": "group/tool", "iids": [17, 18]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_gitlab_issue_discussions_empty_without_config_or_on_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabIssueDiscussionsAdapter(config={"project_id": 1, "issue_iids": [2]}).fetch() == []
    assert await GitLabIssueDiscussionsAdapter(token="token", config={"project_id": 1}).fetch() == []
    assert await GitLabIssueDiscussionsAdapter(token="token", config={"project_id": 1, "issue_iids": [2]}).fetch(limit=0) == []

    failing = GitLabIssueDiscussionsAdapter(
        token="token",
        config={"project_id": 1, "issue_iids": [2]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
