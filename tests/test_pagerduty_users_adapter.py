"""Tests for PagerDuty users import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.pagerduty_users_adapter import PagerDutyUserAdapter, PagerDutyUsersAdapter


def _user(number: int, *, include_optional: bool = True) -> dict:
    user = {
        "id": f"PUSER{number}",
        "name": f"Responder {number}",
        "summary": f"Responder {number}",
        "email": f"responder{number}@example.com",
        "role": "admin",
        "time_zone": "Asia/Tokyo",
        "created_at": f"2026-05-{number:02d}T00:00:00Z",
        "updated_at": f"2026-05-{number + 1:02d}T00:00:00Z",
        "html_url": f"https://acme.pagerduty.com/users/PUSER{number}",
    }
    if include_optional:
        user["job_title"] = "Incident Commander"
        user["contact_methods"] = [
            {
                "id": "PCM1",
                "type": "email_contact_method",
                "summary": "Work email",
                "label": "Work",
                "address": f"responder{number}@example.com",
            },
            {"id": "PCM2", "type": "phone_contact_method", "label": "Mobile", "address": "+15550100"},
        ]
        user["teams"] = [
            {
                "id": "PTEAM1",
                "summary": "Platform",
                "type": "team_reference",
                "html_url": "https://acme.pagerduty.com/teams/PTEAM1",
            }
        ]
    return user


@pytest.mark.asyncio
async def test_pagerduty_users_fetches_filters_paginates_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"users": [_user(1)], "limit": 1, "offset": 0, "more": True})
        return httpx.Response(200, json={"users": [_user(2)], "limit": 1, "offset": 1, "more": False})

    adapter = PagerDutyUsersAdapter(
        api_token="pd-token",
        from_email="max@example.com",
        api_url="https://api.pagerduty.test",
        config={"team_ids": ["PTEAM1"], "query": "responder", "include": ["contact_methods", "teams"], "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert PagerDutyUserAdapter is PagerDutyUsersAdapter
    assert [request.url.params["offset"] for request in requests] == ["0", "1"]
    assert requests[0].url.path == "/users"
    assert requests[0].headers["Authorization"] == "Token token=pd-token"
    assert requests[0].headers["From"] == "max@example.com"
    assert requests[0].url.params["team_ids[]"] == "PTEAM1"
    assert requests[0].url.params["query"] == "responder"
    assert requests[0].url.params["include[]"] == "contact_methods"
    assert requests[0].url.params["limit"] == "1"
    assert len(signals) == 2
    assert signals[0].id == "pagerduty-user:PUSER1"
    assert signals[0].source_adapter == "pagerduty_users_import"
    assert signals[0].source_type.value == "failure_data"
    assert signals[0].title == "PagerDuty user Responder 1"
    assert signals[0].author == "Responder 1"
    assert signals[0].url == "https://acme.pagerduty.com/users/PUSER1"
    assert signals[0].metadata["user_id"] == "PUSER1"
    assert signals[0].metadata["email"] == "responder1@example.com"
    assert signals[0].metadata["role"] == "admin"
    assert signals[0].metadata["job_title"] == "Incident Commander"
    assert signals[0].metadata["time_zone"] == "Asia/Tokyo"
    assert signals[0].metadata["contact_methods"][0]["summary"] == "Work email"
    assert signals[0].metadata["contact_methods_summary"] == ["Work email", "Mobile"]
    assert signals[0].metadata["teams"][0]["id"] == "PTEAM1"
    assert signals[0].metadata["created_at"] == "2026-05-01T00:00:00Z"
    assert "operations" in signals[0].tags


@pytest.mark.asyncio
async def test_pagerduty_users_handles_missing_optional_contact_and_team_data() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"users": [_user(1, include_optional=False)], "more": False})

    adapter = PagerDutyUsersAdapter(
        api_token="pd-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["job_title"] is None
    assert signals[0].metadata["contact_methods"] == []
    assert signals[0].metadata["contact_methods_summary"] == []
    assert signals[0].metadata["teams"] == []


@pytest.mark.asyncio
async def test_pagerduty_users_reads_env_token_and_caps_config_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAGERDUTY_API_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"users": [_user(1), _user(2)], "more": False})

    adapter = PagerDutyUsersAdapter(
        config={"limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert requests[0].headers["Authorization"] == "Token token=env-token"
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_pagerduty_users_missing_token_non_positive_limit_and_failures_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PAGERDUTY_API_TOKEN", raising=False)
    monkeypatch.delenv("PAGERDUTY_TOKEN", raising=False)

    assert await PagerDutyUsersAdapter().fetch() == []
    assert await PagerDutyUsersAdapter(api_token="pd-token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = PagerDutyUsersAdapter(
        api_token="pd-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch(limit=2) == []
