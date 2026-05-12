"""Tests for GitLab merge request approvals import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_merge_request_approvals_adapter import (
    GitLabMergeRequestApprovalsAdapter,
)


APPROVAL = {
    "id": 7001,
    "iid": 17,
    "project_id": 278964,
    "title": "Release the workflow adapter",
    "description": "Approval data for the merge request.",
    "state": "opened",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T10:05:00Z",
    "web_url": "https://gitlab.example/group/tool/-/merge_requests/17",
    "approved": True,
    "approvals_required": 2,
    "approvals_left": 0,
    "user_has_approved": False,
    "user_can_approve": True,
    "approval_rules_overwritten": False,
    "approved_by": [
        {
            "user": {
                "id": 101,
                "username": "reviewer",
                "name": "Reviewer One",
                "web_url": "https://gitlab.example/reviewer",
                "avatar_url": "https://gitlab.example/uploads/reviewer.png",
            }
        }
    ],
}


@pytest.mark.asyncio
async def test_gitlab_merge_request_approvals_fetches_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=APPROVAL)

    adapter = GitLabMergeRequestApprovalsAdapter(
        token="gitlab_token",
        api_url="https://gitlab.example/api/v4",
        config={"merge_requests": [{"project_id": "group/tool", "iid": 17}]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 1
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab_token"
    assert requests[0].headers["User-Agent"] == "max-gitlab-merge-request-approvals-import/1"
    assert str(requests[0].url) == (
        "https://gitlab.example/api/v4/projects/group%2Ftool/merge_requests/17/approvals"
    )
    assert len(signals) == 1

    signal = signals[0]
    assert signal.id == "gitlab-mr-approval:278964:17"
    assert signal.source_adapter == "gitlab_merge_request_approvals_import"
    assert signal.title == "278964 !17 approved: Release the workflow adapter"
    assert signal.url == "https://gitlab.example/group/tool/-/merge_requests/17"
    assert signal.author == "reviewer"
    assert signal.metadata["project_id"] == "278964"
    assert signal.metadata["merge_request_iid"] == "17"
    assert signal.metadata["merge_request_id"] == 7001
    assert signal.metadata["approved"] is True
    assert signal.metadata["state"] == "approved"
    assert signal.metadata["approvals_required"] == 2
    assert signal.metadata["approvals_left"] == 0
    assert signal.metadata["approved_by"][0]["username"] == "reviewer"
    assert signal.metadata["approver_usernames"] == ["reviewer"]
    assert signal.metadata["raw"] == APPROVAL
    assert "approval" in signal.tags


@pytest.mark.asyncio
async def test_gitlab_merge_request_approvals_uses_project_and_iid_config_with_url_encoding() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={**APPROVAL, "approved": False, "approvals_left": 1})

    adapter = GitLabMergeRequestApprovalsAdapter(
        token="gitlab_token",
        api_url="https://gitlab.example/api/v4/",
        config={"project_ids": ["group/sub/tool"], "merge_request_iids": [42]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert str(requests[0].url) == (
        "https://gitlab.example/api/v4/projects/group%2Fsub%2Ftool/merge_requests/42/approvals"
    )
    assert signals[0].metadata["state"] == "unapproved"
    assert signals[0].metadata["approvals_left"] == 1


@pytest.mark.asyncio
async def test_gitlab_merge_request_approvals_env_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=APPROVAL)

    monkeypatch.setenv("GITLAB_PRIVATE_TOKEN", "private-token")
    monkeypatch.setenv("GITLAB_API_URL", "https://gitlab.env/api/v4")

    adapter = GitLabMergeRequestApprovalsAdapter(
        config={"merge_requests": [{"project_id": "group/tool", "iid": "17"}]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert requests[0].headers["PRIVATE-TOKEN"] == "private-token"
    assert str(requests[0].url).startswith("https://gitlab.env/api/v4/")


@pytest.mark.asyncio
async def test_gitlab_merge_request_approvals_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert (
        await GitLabMergeRequestApprovalsAdapter(
            config={"merge_requests": [{"project_id": "group/tool", "iid": 17}]}
        ).fetch()
        == []
    )
    assert await GitLabMergeRequestApprovalsAdapter(token="token").fetch() == []
    assert (
        await GitLabMergeRequestApprovalsAdapter(
            token="token",
            config={"merge_requests": [{"project_id": "group/tool", "iid": 17}]},
        ).fetch(limit=0)
        == []
    )


@pytest.mark.asyncio
async def test_gitlab_merge_request_approvals_http_failure_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = GitLabMergeRequestApprovalsAdapter(
        token="gitlab_token",
        config={"merge_requests": [{"project_id": "group/tool", "iid": 17}]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=1) == []
