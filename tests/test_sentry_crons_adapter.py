"""Tests for Sentry cron monitors import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_crons_adapter import SentryCronsAdapter
from max.types.signal import SignalSourceType


def _monitor(monitor_id: str, *, name: str = "Nightly Sync", status: str = "active") -> dict:
    return {
        "id": monitor_id,
        "slug": f"{monitor_id}-slug",
        "name": name,
        "status": status,
        "config": {"schedule": [1, "day"]},
        "project": {"slug": "web"},
        "environment": "production",
        "owner": {"name": "Data Platform", "slug": "data-platform"},
        "dateCreated": "2026-05-01T09:00:00Z",
        "dateModified": "2026-05-02T10:00:00Z",
        "nextCheckIn": "2026-05-03T09:00:00Z",
        "latestCheckIn": {
            "id": f"checkin-{monitor_id}",
            "status": "ok",
            "dateCreated": "2026-05-02T09:00:00Z",
            "environment": "production",
        },
        "url": f"https://sentry.example/organizations/acme/crons/{monitor_id}-slug/",
    }


@pytest.mark.asyncio
async def test_sentry_crons_fetches_pages_and_maps_monitor_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[_monitor("mon-1")],
                headers={"Link": '<https://sentry.example/api/0/organizations/acme/monitors/?cursor=next>; rel="next"; results="true"'},
            )
        return httpx.Response(
            200,
            json=[_monitor("mon-2", name="Hourly Import", status="disabled")],
            headers={"Link": '<https://sentry.example/api/0/organizations/acme/monitors/?cursor=end>; rel="next"; results="false"'},
        )

    adapter = SentryCronsAdapter(
        auth_token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={
            "organization_slug": "acme",
            "project_slug": "web",
            "page_size": 1,
            "status": "active",
            "environment": "production",
            "query": "nightly",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/organizations/acme/monitors/"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["project"] == "web"
    assert requests[0].url.params["status"] == "active"
    assert requests[0].url.params["environment"] == "production"
    assert requests[0].url.params["query"] == "nightly"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert requests[1].url.params["cursor"] == "next"
    assert [signal.metadata["sentry_monitor_id"] for signal in signals] == ["mon-1", "mon-2"]

    signal = signals[0]
    assert signal.id == "sentry-cron-monitor:mon-1"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "sentry_crons_import"
    assert signal.title == "Nightly Sync"
    assert signal.url == "https://sentry.example/organizations/acme/crons/mon-1-slug/"
    assert signal.author == "Data Platform"
    assert signal.published_at is not None
    assert signal.metadata["sentry_organization_slug"] == "acme"
    assert signal.metadata["sentry_monitor_slug"] == "mon-1-slug"
    assert signal.metadata["sentry_project_slug"] == "web"
    assert signal.metadata["status"] == "active"
    assert signal.metadata["schedule"] == "every 1 day"
    assert signal.metadata["checkin_health"] == "ok"
    assert signal.metadata["environment"] == "production"
    assert signal.metadata["owner"] == "Data Platform"
    assert signal.metadata["date_created"] == "2026-05-01T09:00:00Z"
    assert signal.metadata["date_modified"] == "2026-05-02T10:00:00Z"
    assert signal.metadata["last_checkin"] == "2026-05-02T09:00:00Z"
    assert signal.metadata["next_checkin"] == "2026-05-03T09:00:00Z"
    assert signal.metadata["latest_checkin"]["id"] == "checkin-mon-1"
    assert signal.metadata["raw"]["id"] == "mon-1"
    assert "cron" in signal.tags


@pytest.mark.asyncio
async def test_sentry_crons_supports_body_cursor_org_scope_and_deduplicates() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            **_monitor("mon-1", name="Crontab Monitor"),
                            "config": {"crontab": "0 12 * * *"},
                            "latestCheckIn": {"status": "missed", "dateCreated": "2026-05-02T12:00:00Z"},
                            "environment": {"name": "staging"},
                        }
                    ],
                    "cursor": {"next": "cursor-2", "hasMore": True},
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    _monitor("mon-1", name="Duplicate"),
                        {
                            **_monitor("mon-3", name="Monitor Environment Health"),
                            "environment": None,
                            "latestCheckIn": {},
                            "monitorEnvironment": {"status": "timeout", "name": "preview"},
                        },
                ],
                "cursor": {"next": "end", "hasMore": False},
            },
        )

    adapter = SentryCronsAdapter(
        token="sentry-token",
        config={"org": "acme", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert "project" not in requests[0].url.params
    assert requests[1].url.params["cursor"] == "cursor-2"
    assert [signal.id for signal in signals] == ["sentry-cron-monitor:mon-1", "sentry-cron-monitor:mon-3"]
    assert signals[0].metadata["schedule"] == "0 12 * * *"
    assert signals[0].metadata["checkin_health"] == "missed"
    assert signals[0].metadata["environment"] == "staging"
    assert signals[1].metadata["checkin_health"] == "timeout"
    assert signals[1].metadata["environment"] == "preview"


@pytest.mark.asyncio
async def test_sentry_crons_respects_per_project_limit_and_aliases() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        project = request.url.params["project"]
        return httpx.Response(200, json=[_monitor(f"{project}-1"), _monitor(f"{project}-2")])

    adapter = SentryCronsAdapter(
        token="sentry-token",
        config={
            "org": "acme",
            "projects": [{"slug": "web"}, {"id": "api"}],
            "page_size": 10,
            "per_project_limit": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.params["per_page"] == "1"
    assert [request.url.params["project"] for request in requests] == ["web", "api"]
    assert [signal.metadata["sentry_monitor_id"] for signal in signals] == ["web-1", "api-1"]


@pytest.mark.asyncio
async def test_sentry_crons_empty_without_required_config_or_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    assert await SentryCronsAdapter(config={"org": "acme"}).fetch() == []
    assert await SentryCronsAdapter(auth_token="token").fetch() == []
    assert await SentryCronsAdapter(auth_token="token", config={"org": "acme"}).fetch(limit=0) == []
