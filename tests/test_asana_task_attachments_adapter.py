"""Tests for Asana task attachments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.asana_task_attachments_adapter import AsanaTaskAttachmentAdapter, AsanaTaskAttachmentsAdapter


def _attachment(number: int, *, gid: str | None = None, task_gid: str = "t1") -> dict:
    attachment_gid = gid or f"a{number}"
    return {
        "gid": attachment_gid,
        "name": f"Attachment {number}.pdf",
        "resource_type": "attachment",
        "resource_subtype": "dropbox",
        "created_at": "2026-05-01T10:00:00Z",
        "download_url": f"https://download.example/{attachment_gid}",
        "permanent_url": f"https://app.asana.com/app/asana/-/get_asset?asset_id={attachment_gid}",
        "view_url": f"https://view.example/{attachment_gid}",
        "host": "dropbox",
        "parent": {"gid": task_gid, "name": f"Task {task_gid}"},
    }


@pytest.mark.asyncio
async def test_asana_task_attachments_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"data": [_attachment(1)], "next_page": {"offset": "next-offset"}},
            )
        return httpx.Response(200, json={"data": [_attachment(2)]})

    adapter = AsanaTaskAttachmentsAdapter(
        access_token="asana-token",
        api_url="https://asana.example/api/1.0",
        config={"task_gid": "t1", "page_size": 1, "opt_fields": ["gid", "name", "download_url"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert AsanaTaskAttachmentAdapter is AsanaTaskAttachmentsAdapter
    assert len(requests) == 2
    assert requests[0].url.path == "/api/1.0/tasks/t1/attachments"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["opt_fields"] == "gid,name,download_url"
    assert requests[0].headers["Authorization"] == "Bearer asana-token"
    assert requests[1].url.params["offset"] == "next-offset"

    signal = signals[0]
    assert signal.id == "asana-task-attachment:t1:a1"
    assert signal.source_adapter == "asana_task_attachments_import"
    assert signal.source_type.value == "roadmap"
    assert signal.title == "Asana attachment Attachment 1.pdf"
    assert signal.url == "https://app.asana.com/app/asana/-/get_asset?asset_id=a1"
    assert signal.metadata["asana_task_gid"] == "t1"
    assert signal.metadata["parent_task_gid"] == "t1"
    assert signal.metadata["attachment_gid"] == "a1"
    assert signal.metadata["name"] == "Attachment 1.pdf"
    assert signal.metadata["resource_subtype"] == "dropbox"
    assert signal.metadata["permanent_url"] == "https://app.asana.com/app/asana/-/get_asset?asset_id=a1"
    assert signal.metadata["download_url"] == "https://download.example/a1"
    assert signal.metadata["host"] == "dropbox"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["raw"]["gid"] == "a1"
    assert "task-attachment" in signal.tags


@pytest.mark.asyncio
async def test_asana_task_attachments_per_task_limit_global_limit_and_dedupes() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        task_gid = request.url.path.split("/")[-2]
        if task_gid == "t1":
            return httpx.Response(200, json={"data": [_attachment(1, gid="shared", task_gid="t1"), _attachment(2, task_gid="t1")]})
        return httpx.Response(200, json={"data": [_attachment(3, gid="shared", task_gid="t2"), _attachment(4, task_gid="t2")]})

    adapter = AsanaTaskAttachmentsAdapter(
        token="asana-token",
        config={"task_gids": ["t1", "t2"], "per_task_limit": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert [signal.metadata["attachment_gid"] for signal in signals] == ["shared", "a2", "a4"]
    assert [signal.metadata["asana_task_gid"] for signal in signals] == ["t1", "t1", "t2"]


@pytest.mark.asyncio
async def test_asana_task_attachments_uses_tasks_config_and_env_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_attachment(1, task_gid="t9")]})

    adapter = AsanaTaskAttachmentsAdapter(
        config={"tasks": [{"gid": "t9"}]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert requests[0].url.path == "/api/1.0/tasks/t9/attachments"


@pytest.mark.asyncio
async def test_asana_task_attachments_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)

    assert await AsanaTaskAttachmentsAdapter(config={"task_gid": "t1"}).fetch() == []
    assert await AsanaTaskAttachmentsAdapter(token="token").fetch() == []
    assert await AsanaTaskAttachmentsAdapter(token="token", config={"task_gid": "t1"}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_asana_task_attachments_failure_returns_partial_results() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"data": [_attachment(1, task_gid="t1")]})
        return httpx.Response(500)

    adapter = AsanaTaskAttachmentsAdapter(
        token="asana-token",
        config={"task_gids": ["t1", "t2"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert [signal.metadata["attachment_gid"] for signal in signals] == ["a1"]
