"""Tests for GitLab project hooks import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_project_hooks_adapter import GitLabProjectHookAdapter, GitLabProjectHooksAdapter


def _hook(number: int, *, enabled: bool = True, include_optional: bool = True) -> dict:
    hook = {
        "id": 100 + number,
        "url": f"https://hooks.example/gitlab/{number}",
        "push_events": enabled,
        "issues_events": False,
        "merge_requests_events": enabled,
        "tag_push_events": False,
        "note_events": enabled,
        "pipeline_events": enabled,
        "created_at": f"2026-05-{number:02d}T10:00:00Z",
    }
    if include_optional:
        hook["push_events_branch_filter"] = "main"
        hook["alert_status"] = "executable"
        hook["disabled_until"] = None
        hook["last_response"] = {"code": 200, "status": "success"}
        hook["recent_failures"] = 0
        hook["enable_ssl_verification"] = True
    return hook


@pytest.mark.asyncio
async def test_gitlab_project_hooks_paginates_and_maps_event_configuration() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_hook(1), _hook(2, enabled=False)])
        return httpx.Response(200, json=[_hook(3)])

    adapter = GitLabProjectHooksAdapter(
        token="gitlab_token",
        base_url="https://gitlab.example/api/v4",
        config={"project_path": "group/tool", "per_page": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert GitLabProjectHookAdapter is GitLabProjectHooksAdapter
    assert len(requests) == 2
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab_token"
    assert requests[0].url.raw_path.startswith(b"/api/v4/projects/group%2Ftool/hooks?")
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "2"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["hook_id"] for signal in signals] == [101, 102, 103]
    assert signals[0].source_adapter == "gitlab_project_hooks_import"
    assert signals[0].source_type.value == "failure_data"
    assert signals[0].title == "GitLab project hook 101"
    assert signals[0].url == "https://hooks.example/gitlab/1"
    assert signals[0].metadata["project_id"] == "group/tool"
    assert signals[0].metadata["url"] == "https://hooks.example/gitlab/1"
    assert signals[0].metadata["event_flags"]["push_events"] is True
    assert signals[0].metadata["event_flags"]["issues_events"] is False
    assert "push_events" in signals[0].metadata["enabled_events"]
    assert "issues_events" in signals[0].metadata["disabled_events"]
    assert signals[0].metadata["push_events_branch_filter"] == "main"
    assert signals[0].metadata["alert_status"] == "executable"
    assert signals[0].metadata["last_response"]["code"] == 200
    assert "project-hook" in signals[0].tags


@pytest.mark.asyncio
async def test_gitlab_project_hooks_records_disabled_events() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_hook(1, enabled=False)])

    adapter = GitLabProjectHooksAdapter(
        token="gitlab_token",
        config={"project_id": "123"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert signals[0].metadata["enabled_events"] == []
    assert set(signals[0].metadata["disabled_events"]) == {
        "push_events",
        "issues_events",
        "merge_requests_events",
        "tag_push_events",
        "note_events",
        "pipeline_events",
    }
    assert "no enabled events" in signals[0].content


@pytest.mark.asyncio
async def test_gitlab_project_hooks_handles_missing_optional_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_hook(1, include_optional=False)])

    adapter = GitLabProjectHooksAdapter(
        token="gitlab_token",
        config={"project_id": "123"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert signals[0].metadata["push_events_branch_filter"] is None
    assert "alert_status" not in signals[0].metadata
    assert "last_response" not in signals[0].metadata
    assert signals[0].published_at is not None


@pytest.mark.asyncio
async def test_gitlab_project_hooks_reads_env_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "env_token")
    monkeypatch.setenv("GITLAB_PROJECT_PATH", "env/project")
    monkeypatch.setenv("GITLAB_API_URL", "https://gitlab.env/api/v4")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_hook(1)])

    adapter = GitLabProjectHooksAdapter(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["PRIVATE-TOKEN"] == "env_token"
    assert requests[0].url.raw_path.startswith(b"/api/v4/projects/env%2Fproject/hooks?")
    assert signals[0].metadata["project_id"] == "env/project"


@pytest.mark.asyncio
async def test_gitlab_project_hooks_empty_without_required_config_or_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_ID", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_PATH", raising=False)

    assert await GitLabProjectHooksAdapter(config={"project_id": "1"}).fetch() == []
    assert await GitLabProjectHooksAdapter(token="token").fetch() == []
    assert await GitLabProjectHooksAdapter(token="token", config={"project_id": "1"}).fetch(limit=0) == []
