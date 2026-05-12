from __future__ import annotations

import httpx
import pytest

from max.imports.shortcut_stories_adapter import ShortcutStoriesAdapter


@pytest.mark.asyncio
async def test_fetches_stories_with_token_filters_and_maps_metadata() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 42,
                        "name": "Export audit trail",
                        "description": "Enterprise admins need audit history.",
                        "app_url": "https://app.shortcut.com/acme/story/42/export-audit-trail",
                        "workflow_state_id": 123,
                        "project_id": 456,
                        "epic_id": 789,
                        "owner_ids": ["owner-1"],
                        "labels": [{"name": "enterprise"}],
                        "archived": False,
                        "story_type": "feature",
                        "estimate": 3,
                        "deadline": "2026-06-01",
                        "created_at": "2026-05-01T10:00:00Z",
                        "updated_at": "2026-05-02T10:00:00Z",
                        "completed_at": None,
                    }
                ]
            },
        )

    adapter = ShortcutStoriesAdapter(
        token="shortcut-token",
        api_url="https://shortcut.example.test/api/v3",
        workflow_state_id=123,
        project_id=456,
        epic_id=789,
        owner_id="owner-1",
        label="enterprise",
        archived=False,
        page_size=50,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert requests[0].headers["Shortcut-Token"] == "shortcut-token"
    assert requests[0].url.path == "/api/v3/search/stories"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["page_size"] == "10"
    query = requests[0].url.params["query"]
    assert "workflow_state_id:123" in query
    assert "project:456" in query
    assert "epic:789" in query
    assert "owner:owner-1" in query
    assert 'label:"enterprise"' in query
    assert "!is:archived" in query
    assert len(signals) == 1
    assert signals[0].source_adapter == "shortcut_stories_import"
    assert signals[0].title == "Export audit trail"
    assert signals[0].content == "Enterprise admins need audit history."
    assert signals[0].url == "https://app.shortcut.com/acme/story/42/export-audit-trail"
    assert signals[0].metadata["shortcut_story_id"] == 42
    assert signals[0].metadata["workflow_state_id"] == 123
    assert signals[0].metadata["project_id"] == 456
    assert signals[0].metadata["epic_id"] == 789
    assert signals[0].metadata["owner_ids"] == ["owner-1"]
    assert signals[0].metadata["labels"] == ["enterprise"]
    assert signals[0].metadata["archived"] is False
    assert signals[0].metadata["story_type"] == "feature"
    assert signals[0].metadata["estimate"] == 3
    assert signals[0].metadata["deadline"] == "2026-06-01"
    assert "shortcut" in signals[0].tags


@pytest.mark.asyncio
async def test_paginates_deduplicates_and_stops_at_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["page"] == "1":
            return httpx.Response(
                200,
                json={"data": [{"id": 1, "name": "One"}, {"id": 1, "name": "Duplicate"}]},
            )
        return httpx.Response(200, json={"data": [{"id": 2, "name": "Two"}]})

    adapter = ShortcutStoriesAdapter(
        token="shortcut-token",
        page_size=2,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["shortcut_story_id"] for signal in signals] == [1, 2]
    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert [request.url.params["page_size"] for request in requests] == ["2", "1"]


@pytest.mark.asyncio
async def test_follows_next_url_without_extra_request_after_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [{"id": 1, "name": "One"}],
                "next": "https://shortcut.example.test/api/v3/search/stories?page=2",
            },
        )

    adapter = ShortcutStoriesAdapter(
        token="shortcut-token",
        api_url="https://shortcut.example.test/api/v3",
        page_size=25,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["One"]
    assert len(requests) == 1
    assert requests[0].url.params["page_size"] == "1"


@pytest.mark.asyncio
async def test_missing_token_limit_and_http_failure_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SHORTCUT_API_TOKEN", raising=False)
    assert await ShortcutStoriesAdapter().fetch() == []
    assert await ShortcutStoriesAdapter(token="token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    adapter = ShortcutStoriesAdapter(
        token="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []


def test_resolves_token_from_argument_config_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHORTCUT_API_TOKEN", "env-token")
    assert ShortcutStoriesAdapter().token == "env-token"
    assert ShortcutStoriesAdapter(config={"api_token": "config-token"}).token == "config-token"
    assert ShortcutStoriesAdapter(token="arg-token", config={"api_token": "config-token"}).token == (
        "arg-token"
    )


def test_configures_optional_filters_and_page_size() -> None:
    adapter = ShortcutStoriesAdapter(
        config={
            "workflow_state_id": 1,
            "project_id": 2,
            "epic_id": 3,
            "owner_id": "owner-1",
            "label": "beta",
            "archived": "true",
            "page_size": 250,
        }
    )

    assert adapter.page_size == 100
    query = adapter._query()
    assert "workflow_state_id:1" in query
    assert "project:2" in query
    assert "epic:3" in query
    assert "owner:owner-1" in query
    assert 'label:"beta"' in query
    assert "is:archived" in query
