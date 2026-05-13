"""Tests for GitLab project labels import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_project_labels_adapter import GitLabProjectLabelsAdapter
from max.types.signal import SignalSourceType


LABEL = {
    "id": 42,
    "name": "planning",
    "color": "#428BCA",
    "text_color": "#FFFFFF",
    "description": "Planning and roadmap work",
    "priority": 3,
    "open_issues_count": 7,
    "closed_issues_count": 11,
    "subscribed": False,
    "is_project_label": True,
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-02T10:00:00Z",
}


@pytest.mark.asyncio
async def test_gitlab_project_labels_fetches_paginates_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[{**LABEL, "id": 1, "name": "planning"}],
                headers={"X-Next-Page": "2"},
            )
        return httpx.Response(
            200,
            json=[{**LABEL, "id": 2, "name": "risk", "web_url": "https://gitlab.example/group/tool/-/labels?subscribed=&search=risk"}],
            headers={"X-Next-Page": ""},
        )

    adapter = GitLabProjectLabelsAdapter(
        token="gitlab-token",
        gitlab_url="https://gitlab.example",
        config={"project_path": "group/tool", "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert [request.url.params["per_page"] for request in requests] == ["1", "1"]
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[0].headers["User-Agent"] == "max-gitlab-project-labels-import/1"
    assert str(requests[0].url).startswith("https://gitlab.example/api/v4/projects/group%2Ftool/labels?")
    assert len(signals) == 2

    signal = signals[0]
    assert signal.id == "gitlab-label:group/tool:1"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "gitlab_project_labels_import"
    assert signal.title == "planning"
    assert signal.content == "Planning and roadmap work; color #428BCA; priority 3; 7 open issues; 11 closed issues"
    assert signal.url == "https://gitlab.example/group/tool/-/labels?search=planning"
    assert signal.author is None
    assert signal.metadata["project_id"] == "group/tool"
    assert signal.metadata["label_id"] == 1
    assert signal.metadata["name"] == "planning"
    assert signal.metadata["color"] == "#428BCA"
    assert signal.metadata["text_color"] == "#FFFFFF"
    assert signal.metadata["description"] == "Planning and roadmap work"
    assert signal.metadata["priority"] == 3
    assert signal.metadata["open_issues_count"] == 7
    assert signal.metadata["closed_issues_count"] == 11
    assert signal.metadata["raw"]["id"] == 1
    assert {"gitlab", "label", "planning"}.issubset(set(signal.tags))
    assert signals[1].url == "https://gitlab.example/group/tool/-/labels?subscribed=&search=risk"


@pytest.mark.asyncio
async def test_gitlab_project_labels_uses_bearer_token_and_config_aliases() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[{**LABEL, "id": "bug", "name": "bug"}])

    adapter = GitLabProjectLabelsAdapter(
        config={
            "bearer_token": "oauth-token",
            "api_url": "https://gitlab.example/api/v4/",
            "project_ids": [278964],
            "page_size": 5,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer oauth-token"
    assert "PRIVATE-TOKEN" not in requests[0].headers
    assert requests[0].url.path == "/api/v4/projects/278964/labels"
    assert requests[0].url.params["per_page"] == "1"
    assert signals[0].metadata["project_id"] == "278964"
    assert signals[0].id == "gitlab-label:278964:bug"


@pytest.mark.asyncio
async def test_gitlab_project_labels_respects_limit_across_projects() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[{**LABEL, "id": len(requests), "name": f"label-{len(requests)}"}])

    adapter = GitLabProjectLabelsAdapter(
        token="gitlab-token",
        config={"projects": ["1", "2"], "per_page": 10},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert [signal.metadata["project_id"] for signal in signals] == ["1"]


@pytest.mark.asyncio
async def test_gitlab_project_labels_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabProjectLabelsAdapter(config={"project_id": 1}).fetch() == []
    assert await GitLabProjectLabelsAdapter(token="token").fetch() == []
    assert await GitLabProjectLabelsAdapter(token="token", config={"project_id": 1}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_gitlab_project_labels_http_failure_or_malformed_response_returns_empty() -> None:
    failing = GitLabProjectLabelsAdapter(
        token="token",
        config={"project_id": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []

    malformed = GitLabProjectLabelsAdapter(
        token="token",
        config={"project_id": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"bad": "shape"}))),
    )
    assert await malformed.fetch(limit=1) == []
