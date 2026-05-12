"""Tests for ServiceNow change requests import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.servicenow_change_requests_adapter import ServiceNowChangeRequestsAdapter
from max.types.signal import SignalSourceType


CHANGE = {
    "sys_id": "sys-1",
    "number": "CHG0001",
    "short_description": "Deploy billing change",
    "description": "Change the billing deployment window",
    "state": "Assess",
    "risk": "High",
    "impact": "2 - Medium",
    "assignment_group": {"display_value": "Platform"},
    "start_date": "2026-05-12 10:00:00",
    "end_date": "2026-05-12 11:00:00",
    "work_start": "2026-05-12 10:05:00",
    "work_end": "2026-05-12 10:55:00",
    "sys_created_on": "2026-05-01 09:00:00",
    "sys_updated_on": "2026-05-02 09:00:00",
    "opened_by": {"display_value": "Ada"},
}


@pytest.mark.asyncio
async def test_servicenow_fetch_maps_change_requests_and_query_params() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"result": [CHANGE]})
        return httpx.Response(200, json={"result": [{**CHANGE, "sys_id": "sys-2", "number": "CHG0002"}]})

    adapter = ServiceNowChangeRequestsAdapter(
        instance_url="https://acme.service-now.com",
        token="snow-token",
        config={"sysparm_query": "state!=Closed", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/now/table/change_request"
    assert requests[0].url.params["sysparm_query"] == "state!=Closed"
    assert requests[0].url.params["sysparm_limit"] == "1"
    assert requests[0].url.params["sysparm_offset"] == "0"
    assert requests[1].url.params["sysparm_offset"] == "1"
    assert requests[0].headers["Authorization"] == "Bearer snow-token"
    assert signals[0].source_type == SignalSourceType.FAILURE_DATA
    assert signals[0].source_adapter == "servicenow_change_requests_import"
    assert signals[0].title == "CHG0001 Deploy billing change"
    assert signals[0].content == "Change the billing deployment window"
    assert signals[0].url == "https://acme.service-now.com/nav_to.do?uri=change_request.do?sys_id=sys-1"
    assert signals[0].author == "Ada"
    assert signals[0].metadata["sys_id"] == "sys-1"
    assert signals[0].metadata["number"] == "CHG0001"
    assert signals[0].metadata["state"] == "Assess"
    assert signals[0].metadata["risk"] == "High"
    assert signals[0].metadata["impact"] == "2 - Medium"
    assert signals[0].metadata["assignment_group"] == "Platform"
    assert signals[0].metadata["start_date"] == "2026-05-12 10:00:00"
    assert signals[0].metadata["end_date"] == "2026-05-12 11:00:00"


@pytest.mark.asyncio
async def test_servicenow_supports_basic_auth_without_token() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"result": [CHANGE]})

    adapter = ServiceNowChangeRequestsAdapter(
        api_url="https://snow.example/api/now/table/change_request",
        username="user",
        password="pass",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await adapter.fetch(limit=1)

    assert "Authorization" in requests[0].headers
    assert requests[0].headers["Authorization"].startswith("Basic ")


@pytest.mark.asyncio
async def test_servicenow_reads_environment_and_returns_empty_for_missing_or_bad_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SERVICENOW_INSTANCE_URL", raising=False)
    monkeypatch.delenv("SERVICENOW_API_TOKEN", raising=False)
    assert await ServiceNowChangeRequestsAdapter().fetch() == []
    assert await ServiceNowChangeRequestsAdapter(instance_url="https://snow.example", token="token").fetch(limit=0) == []

    monkeypatch.setenv("SERVICENOW_INSTANCE_URL", "https://env.service-now.com")
    monkeypatch.setenv("SERVICENOW_API_TOKEN", "env-token")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": []})

    adapter = ServiceNowChangeRequestsAdapter(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert adapter.api_url == "https://env.service-now.com/api/now/table/change_request"
    assert adapter.token == "env-token"
    assert await adapter.fetch() == []


@pytest.mark.asyncio
async def test_servicenow_api_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = ServiceNowChangeRequestsAdapter(
        instance_url="https://snow.example",
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch() == []
