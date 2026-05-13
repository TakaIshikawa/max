"""Tests for Sentry project issue alerts import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_project_issue_alerts_adapter import (
    SentryProjectIssueAlertAdapter,
    SentryProjectIssueAlertsAdapter,
)
from max.types.signal import SignalSourceType


def _rule(rule_id: str, *, name: str | None = None, environment: str | None = "production") -> dict:
    rule = {
        "id": rule_id,
        "name": name or f"Alert {rule_id}",
        "actionMatch": "all",
        "filterMatch": "any",
        "frequency": 30,
        "dateCreated": "2026-05-01T10:00:00Z",
        "dateModified": "2026-05-02T10:00:00Z",
        "actions": [{"id": "sentry.rules.actions.notify_event.NotifyEventAction"}],
        "conditions": [{"id": "sentry.rules.conditions.first_seen_event.FirstSeenEventCondition"}],
        "filters": [{"id": "sentry.rules.filters.issue_occurrences.IssueOccurrencesFilter", "value": 10}],
        "url": f"https://sentry.example/alerts/rules/{rule_id}/",
    }
    if environment is not None:
        rule["environment"] = environment
    return rule


@pytest.mark.asyncio
async def test_sentry_project_issue_alerts_fetches_pages_and_maps_alert_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[_rule("1", name="New issue in production")],
                headers={"Link": '<https://sentry.example/api/0/projects/acme/web/rules/?cursor=next>; rel="next"; results="true"'},
            )
        return httpx.Response(
            200,
            json=[_rule("2", environment=None)],
            headers={"Link": '<https://sentry.example/api/0/projects/acme/web/rules/?cursor=end>; rel="next"; results="false"'},
        )

    adapter = SentryProjectIssueAlertsAdapter(
        auth_token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={"organization_slug": "acme", "project_slug": "web", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert SentryProjectIssueAlertAdapter is SentryProjectIssueAlertsAdapter
    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/projects/acme/web/rules/"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[1].url.params["cursor"] == "next"
    assert [signal.metadata["rule_id"] for signal in signals] == ["1", "2"]

    signal = signals[0]
    assert signal.id == "sentry-issue-alert:web:1"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "sentry_project_issue_alerts_import"
    assert signal.title == "New issue in production"
    assert signal.url == "https://sentry.example/alerts/rules/1/"
    assert signal.metadata["signal_role"] == "problem"
    assert signal.metadata["sentry_project_slug"] == "web"
    assert signal.metadata["sentry_alert_rule_id"] == "1"
    assert signal.metadata["action_match"] == "all"
    assert signal.metadata["filter_match"] == "any"
    assert signal.metadata["frequency"] == 30
    assert signal.metadata["environment"] == "production"
    assert signal.metadata["actions"][0]["id"] == "sentry.rules.actions.notify_event.NotifyEventAction"
    assert signal.metadata["conditions"][0]["id"] == "sentry.rules.conditions.first_seen_event.FirstSeenEventCondition"
    assert signal.metadata["filters"][0]["value"] == 10
    assert signal.metadata["raw"]["id"] == "1"
    assert "sentry" in signal.tags
    assert "alert" in signal.tags


@pytest.mark.asyncio
async def test_sentry_project_issue_alerts_supports_config_aliases_cursor_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_rule("1"), _rule("2")])

    adapter = SentryProjectIssueAlertsAdapter(
        token="sentry-token",
        config={"org": "acme", "project": "api", "cursor": "start", "per_page": 50},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].url.path == "/api/0/projects/acme/api/rules/"
    assert requests[0].url.params["cursor"] == "start"
    assert requests[0].url.params["per_page"] == "1"
    assert [signal.metadata["rule_id"] for signal in signals] == ["1"]


@pytest.mark.asyncio
async def test_sentry_project_issue_alerts_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    assert await SentryProjectIssueAlertsAdapter(config={"org": "acme", "project": "web"}).fetch() == []
    assert await SentryProjectIssueAlertsAdapter(auth_token="token", config={"project": "web"}).fetch() == []
    assert await SentryProjectIssueAlertsAdapter(auth_token="token", config={"org": "acme"}).fetch() == []
    assert await SentryProjectIssueAlertsAdapter(auth_token="token", config={"org": "acme", "project": "web"}).fetch(limit=0) == []
