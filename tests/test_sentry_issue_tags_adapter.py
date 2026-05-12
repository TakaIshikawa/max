"""Tests for Sentry issue tags import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_issue_tags_adapter import (
    SentryIssueTagsAdapter,
    SentryIssueTagsImportAdapter,
)
from max.types.signal import SignalSourceType


def _tags() -> list[dict]:
    return [
        {"key": "environment", "name": "Environment", "totalValues": 2},
        {"key": "release", "name": "Release", "totalValues": 3},
        {"key": "logger", "name": "Logger", "totalValues": 10},
    ]


def _values(key: str) -> list[dict]:
    if key == "environment":
        return [
            {"value": "production", "count": 8, "firstSeen": "2026-05-01T10:00:00Z"},
            {"value": "staging", "count": 2},
        ]
    return [
        {"value": "web@1.2.3", "count": 5, "firstSeen": "2026-05-02T10:00:00Z"},
        {"value": "web@1.2.2", "count": 1},
    ]


@pytest.mark.asyncio
async def test_sentry_issue_tags_fetches_tags_then_values_and_maps_distribution_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/0/issues/123/tags/":
            return httpx.Response(200, json=_tags())
        key = request.url.path.split("/")[-3]
        return httpx.Response(200, json=_values(key))

    adapter = SentryIssueTagsImportAdapter(
        auth_token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={"organization_slug": "acme", "issue_ids": ["123"], "key_filters": ["environment", "release"], "page_size": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert SentryIssueTagsAdapter is SentryIssueTagsImportAdapter
    assert [request.url.path for request in requests] == [
        "/api/0/issues/123/tags/",
        "/api/0/issues/123/tags/environment/values/",
        "/api/0/issues/123/tags/release/values/",
    ]
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert [signal.metadata["tag_key"] for signal in signals] == ["environment", "release"]

    signal = signals[0]
    assert signal.id == "sentry-issue-tag:123:environment"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "sentry_issue_tags_import"
    assert signal.title == "Sentry issue 123 tag distribution: environment"
    assert signal.content == "Top environment value for issue 123: production (8)"
    assert signal.url == "https://sentry.example/organizations/acme/issues/?query=issue.id%3A123%20environment%3Aproduction"
    assert signal.published_at is not None
    assert signal.metadata["sentry_issue_id"] == "123"
    assert signal.metadata["issue_id"] == "123"
    assert signal.metadata["top_value"] == "production"
    assert signal.metadata["value_counts"] == {"production": 8, "staging": 2}
    assert signal.metadata["total_values"] == 2
    assert signal.metadata["query_url"] == signal.url
    assert signal.metadata["raw_tag"]["key"] == "environment"
    assert signal.metadata["raw_values"][0]["value"] == "production"
    assert "environment" in signal.tags


@pytest.mark.asyncio
async def test_sentry_issue_tags_uses_default_high_signal_keys_and_cursor_values() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/tags/"):
            return httpx.Response(
                200,
                json=[
                    {"key": "browser", "totalValues": 2},
                    {"key": "device", "totalValues": 1},
                    {"key": "unselected", "totalValues": 9},
                ],
            )
        if len([item for item in requests if item.url.path.endswith("/values/")]) == 1:
            return httpx.Response(
                200,
                json=[{"value": "Chrome", "count": 4}],
                headers={
                    "Link": '<https://sentry.example/api/0/issues/321/tags/browser/values/?cursor=next>; rel="next"; results="true"; cursor="next"'
                },
            )
        return httpx.Response(
            200,
            json=[{"value": "Safari", "count": 2}],
            headers={
                "Link": '<https://sentry.example/api/0/issues/321/tags/browser/values/?cursor=end>; rel="next"; results="false"; cursor="end"'
            },
        )

    adapter = SentryIssueTagsImportAdapter(
        token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={"issue_ids": ["321"], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert requests[1].url.path == "/api/0/issues/321/tags/browser/values/"
    assert requests[2].url.params["cursor"] == "next"
    assert [signal.metadata["tag_key"] for signal in signals] == ["browser", "device"]
    assert signals[0].metadata["value_counts"] == {"Chrome": 4, "Safari": 2}
    assert signals[0].metadata["top_value"] == "Chrome"


@pytest.mark.asyncio
async def test_sentry_issue_tags_respects_limits_across_issues_and_partial_failures() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/0/issues/1/tags/":
            return httpx.Response(200, json=[{"key": "handled", "totalValues": 1}])
        if request.url.path == "/api/0/issues/1/tags/handled/values/":
            return httpx.Response(200, json=[{"value": "false", "count": 12}])
        return httpx.Response(500)

    adapter = SentryIssueTagsImportAdapter(
        auth_token="sentry-token",
        config={"issue_ids": ["1", "2"], "key_filters": ["handled"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 3
    assert len(signals) == 1
    assert signals[0].metadata["issue_id"] == "1"
    assert signals[0].metadata["tag_key"] == "handled"
    assert signals[0].metadata["top_value"] == "false"


@pytest.mark.asyncio
async def test_sentry_issue_tags_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    assert await SentryIssueTagsImportAdapter(config={"issue_ids": ["1"]}).fetch() == []
    assert await SentryIssueTagsImportAdapter(auth_token="token").fetch() == []
    assert await SentryIssueTagsImportAdapter(auth_token="token", config={"issue_ids": ["1"]}).fetch(limit=0) == []
