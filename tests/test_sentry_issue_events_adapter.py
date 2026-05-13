"""Tests for Sentry issue events import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_issue_events_adapter import SentryIssueEventsAdapter
from max.types.signal import SignalSourceType


def _event(event_id: str) -> dict:
    return {
        "id": event_id,
        "title": f"TypeError: failure {event_id}",
        "message": "TypeError exploded",
        "culprit": "app.views.checkout",
        "platform": "python",
        "release": {"version": "backend@1.2.3"},
        "environment": "production",
        "dateCreated": "2026-05-03T12:00:00Z",
        "web_url": f"https://sentry.example/issues/123/events/{event_id}/",
        "tags": [{"key": "customer", "value": "acme"}],
    }


@pytest.mark.asyncio
async def test_sentry_issue_events_fetches_cursor_pages_and_maps_events() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[_event("e1")],
                headers={"Link": '<https://sentry.example/api/0/issues/123/events/?cursor=next-cursor>; rel="next"; results="true"; cursor="next-cursor"'},
            )
        return httpx.Response(200, json=[_event("e2")], headers={"Link": '<https://sentry.example/api/0/issues/123/events/?cursor=end>; rel="next"; results="false"; cursor="end"'})

    adapter = SentryIssueEventsAdapter(
        token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={"issue_ids": ["123"], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/issues/123/events/"
    assert requests[0].url.params["per_page"] == "1"
    assert "cursor" not in requests[0].url.params
    assert requests[1].url.params["cursor"] == "next-cursor"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert [signal.metadata["sentry_event_id"] for signal in signals] == ["e1", "e2"]
    signal = signals[0]
    assert signal.id == "sentry-issue-event:123:e1"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "sentry_issue_events_import"
    assert signal.title == "Sentry issue 123 event e1"
    assert "culprit app.views.checkout" in signal.content
    assert signal.url == "https://sentry.example/issues/123/events/e1/"
    assert signal.metadata["sentry_issue_id"] == "123"
    assert signal.metadata["culprit"] == "app.views.checkout"
    assert signal.metadata["platform"] == "python"
    assert signal.metadata["release"] == "backend@1.2.3"
    assert signal.metadata["environment"] == "production"
    assert signal.metadata["tags"][0]["value"] == "acme"
    assert "issue-event" in signal.tags


@pytest.mark.asyncio
async def test_sentry_issue_events_uses_response_pagination_metadata_until_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"data": [_event("e1")], "pagination": {"hasNext": True, "next": "cursor-2"}})
        return httpx.Response(200, json={"data": [_event("e2")], "pagination": {"hasNext": False}})

    adapter = SentryIssueEventsAdapter(
        auth_token="sentry-token",
        config={"issue_id": "123", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[1].url.params["cursor"] == "cursor-2"
    assert [signal.metadata["sentry_event_id"] for signal in signals] == ["e1", "e2"]


@pytest.mark.asyncio
async def test_sentry_issue_events_empty_without_required_config_or_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    assert await SentryIssueEventsAdapter(config={"issue_ids": ["1"]}).fetch() == []
    assert await SentryIssueEventsAdapter(token="token").fetch() == []
    assert await SentryIssueEventsAdapter(token="token", config={"issue_ids": ["1"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_sentry_issue_events_failure_returns_partial_results() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/issues/1/events/"):
            return httpx.Response(200, json=[_event("e1")])
        return httpx.Response(500)

    adapter = SentryIssueEventsAdapter(
        token="sentry-token",
        config={"issue_ids": ["1", "2"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert [signal.metadata["sentry_event_id"] for signal in signals] == ["e1"]
