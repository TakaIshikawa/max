"""Tests for Jira Service Management requests import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.jira_service_management_requests_adapter import JiraServiceManagementRequestsAdapter
from max.types.signal import SignalSourceType


REQUEST = {
    "issueId": "10001",
    "requestId": "77",
    "issueKey": "HELP-77",
    "summary": "Customer cannot export report",
    "issueUrl": "https://acme.atlassian.net/browse/HELP-77",
    "currentStatus": {"status": "Waiting for support", "statusCategory": "NEW"},
    "requestType": {"id": "rt-1", "name": "Get IT help"},
    "serviceDesk": {"id": "sd-1", "name": "Support"},
    "reporter": {"displayName": "Rhea", "emailAddress": "rhea@example.com"},
    "createdDate": {"iso8601": "2026-05-01T10:00:00+0000"},
    "updatedDate": {"iso8601": "2026-05-02T10:00:00+0000"},
}


@pytest.mark.asyncio
async def test_jsm_fetch_uses_cloud_endpoint_filters_paginates_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"start": 0, "limit": 1, "isLastPage": False, "values": [REQUEST]})
        return httpx.Response(200, json={"start": 1, "limit": 1, "isLastPage": True, "values": [{**REQUEST, "issueKey": "HELP-78"}]})

    adapter = JiraServiceManagementRequestsAdapter(
        cloud_id="cloud-1",
        bearer_token="jsm-token",
        config={"service_desk_id": "sd-1", "request_type_id": "rt-1", "status": "open", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/ex/jira/cloud-1/rest/servicedeskapi/request"
    assert requests[0].url.params["serviceDeskId"] == "sd-1"
    assert requests[0].url.params["requestTypeId"] == "rt-1"
    assert requests[0].url.params["requestStatus"] == "open"
    assert requests[0].url.params["start"] == "0"
    assert requests[1].url.params["start"] == "1"
    assert requests[0].headers["Authorization"] == "Bearer jsm-token"
    assert signals[0].source_type == SignalSourceType.ROADMAP
    assert signals[0].source_adapter == "jira_service_management_requests_import"
    assert signals[0].title == "Customer cannot export report"
    assert signals[0].url == "https://acme.atlassian.net/browse/HELP-77"
    assert signals[0].author == "Rhea"
    assert signals[0].metadata["request_key"] == "HELP-77"
    assert signals[0].metadata["status"] == "Waiting for support"
    assert signals[0].metadata["request_type"] == "Get IT help"
    assert signals[0].metadata["service_desk"] == "Support"
    assert signals[0].metadata["reporter_email"] == "rhea@example.com"
    assert signals[0].metadata["created_at"] == "2026-05-01T10:00:00+0000"
    assert signals[0].metadata["updated_at"] == "2026-05-02T10:00:00+0000"


@pytest.mark.asyncio
async def test_jsm_site_url_supports_basic_auth_without_bearer() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"isLastPage": True, "values": [REQUEST]})

    adapter = JiraServiceManagementRequestsAdapter(
        site_url="https://acme.atlassian.net",
        email="user@example.com",
        token="api-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await adapter.fetch(limit=1)

    assert requests[0].url.path == "/rest/servicedeskapi/request"
    assert requests[0].headers["Authorization"].startswith("Basic ")


@pytest.mark.asyncio
async def test_jsm_empty_for_missing_config_or_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JIRA_SERVICE_MANAGEMENT_TOKEN", raising=False)
    assert await JiraServiceManagementRequestsAdapter(cloud_id="cloud-1").fetch() == []
    assert await JiraServiceManagementRequestsAdapter(site_url="https://jira.test", bearer_token="token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    adapter = JiraServiceManagementRequestsAdapter(
        cloud_id="cloud-1",
        bearer_token="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []
