"""Tests for Opsgenie teams import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.opsgenie_teams_adapter import OpsgenieTeamsImportAdapter
from max.types.signal import SignalSourceType


TEAM = {
    "id": "team-1",
    "name": "Incident Response",
    "description": "Primary incident owners",
    "memberCount": 2,
    "members": [
        {"id": "member-1", "username": "ada@example.com", "fullName": "Ada Lovelace", "role": "admin"},
        {"user": {"id": "user-2", "username": "grace@example.com", "fullName": "Grace Hopper"}, "role": "user"},
    ],
    "tags": ["platform", "sev1"],
    "createdAt": "2026-05-01T10:00:00Z",
}


@pytest.mark.asyncio
async def test_opsgenie_teams_fetches_with_auth_params_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [TEAM], "paging": {}})

    adapter = OpsgenieTeamsImportAdapter(
        api_key="ops-key",
        api_url="https://api.opsgenie.test",
        config={"query": "incident", "page_size": 25, "offset": 5},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert requests[0].url.path == "/v2/teams"
    assert requests[0].url.params["query"] == "incident"
    assert requests[0].url.params["limit"] == "10"
    assert requests[0].url.params["offset"] == "5"
    assert requests[0].headers["Authorization"] == "GenieKey ops-key"
    assert requests[0].headers["User-Agent"] == "max-opsgenie-teams-import/1"

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "opsgenie-team:team-1"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "opsgenie_teams_import"
    assert signal.title == "Incident Response"
    assert signal.metadata["team_id"] == "team-1"
    assert signal.metadata["name"] == "Incident Response"
    assert signal.metadata["description"] == "Primary incident owners"
    assert signal.metadata["member_count"] == 2
    assert signal.metadata["members"][0]["username"] == "ada@example.com"
    assert signal.metadata["members"][1]["id"] == "user-2"
    assert signal.metadata["tags"] == ["platform", "sev1"]
    assert signal.metadata["raw"] == TEAM
    assert {"opsgenie", "team", "platform", "sev1"}.issubset(set(signal.tags))


@pytest.mark.asyncio
async def test_opsgenie_teams_paginates_while_paging_indicates_next() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["offset"] == "3":
            return httpx.Response(
                200,
                json={"data": [{**TEAM, "id": "team-1"}], "offset": 3, "limit": 1, "paging": {"next": "https://next"}},
            )
        return httpx.Response(200, json={"data": [{**TEAM, "id": "team-2"}], "offset": 4, "limit": 1, "paging": {}})

    adapter = OpsgenieTeamsImportAdapter(
        api_key="ops-key",
        config={"page_size": 1, "offset": 3},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["offset"] for request in requests] == ["3", "4"]
    assert [signal.metadata["team_id"] for signal in signals] == ["team-1", "team-2"]


@pytest.mark.asyncio
async def test_opsgenie_teams_supports_data_wrapped_paging_and_empty_results() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"data": {"teams": [{**TEAM, "id": "team-1"}], "offset": 0, "limit": 1, "paging": {"next": "next"}}},
            )
        return httpx.Response(200, json={"data": {"teams": []}})

    adapter = OpsgenieTeamsImportAdapter(
        api_key="ops-key",
        config={"page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert [request.url.params["offset"] for request in requests] == ["0", "1"]
    assert [signal.metadata["team_id"] for signal in signals] == ["team-1"]


@pytest.mark.asyncio
async def test_opsgenie_teams_empty_without_auth_non_positive_limit_or_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPSGENIE_API_KEY", raising=False)
    assert await OpsgenieTeamsImportAdapter().fetch() == []
    assert await OpsgenieTeamsImportAdapter(api_key="key").fetch(limit=0) == []

    empty = OpsgenieTeamsImportAdapter(
        api_key="key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))),
    )
    assert await empty.fetch(limit=10) == []

    failing = OpsgenieTeamsImportAdapter(
        api_key="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )
    assert await failing.fetch(limit=10) == []
