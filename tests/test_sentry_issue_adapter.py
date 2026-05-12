"""Tests for Sentry issue import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_adapter import SentryIssueAdapter
from max.types.signal import SignalSourceType


@pytest.mark.asyncio
async def test_sentry_fetch_maps_and_deduplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "sentry_env")
    requests: list[httpx.Request] = []
    issue = {"id": "i1", "shortId": "MAX-1", "title": "TypeError", "culprit": "app.views", "level": "error", "status": "unresolved", "count": "12", "userCount": 3, "firstSeen": "2026-05-01T00:00:00Z", "lastSeen": "2026-05-02T00:00:00Z", "permalink": "https://sentry.test/i1", "tags": [{"key": "browser", "value": "Chrome"}]}

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[issue, issue])

    adapter = SentryIssueAdapter(config={"organization_slug": "org", "project_slugs": ["proj"], "statuses": ["unresolved"]}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].source_type == SignalSourceType.FAILURE_DATA
    assert signals[0].metadata["sentry_issue_id"] == "i1"
    assert signals[0].metadata["count"] == 12
    assert requests[0].headers["Authorization"] == "Bearer sentry_env"


@pytest.mark.asyncio
async def test_sentry_missing_token_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)
    assert await SentryIssueAdapter(config={"organization_slug": "org"}).fetch() == []
