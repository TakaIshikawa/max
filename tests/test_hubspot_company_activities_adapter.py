"""Tests for HubSpot company activities import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_company_activities_adapter import (
    HubSpotCompanyActivitiesAdapter,
    HubSpotCompanyActivityAdapter,
)


def _activity(activity_id: str, activity_type: str, *, company_id: str = "company-1") -> dict:
    singular = activity_type[:-1]
    props_by_type = {
        "calls": {
            "hs_call_title": "Discovery call",
            "hs_call_body": "Customer asked for rollout timing.",
            "hs_timestamp": "2026-05-01T10:00:00Z",
            "hubspot_owner_id": "owner-1",
            "hs_call_direction": "OUTBOUND",
            "hs_call_status": "COMPLETED",
            "createdate": "2026-05-01T09:59:00Z",
            "hs_lastmodifieddate": "2026-05-01T10:05:00Z",
        },
        "emails": {
            "hs_email_subject": "Security follow-up",
            "hs_email_text": "Shared the security checklist.",
            "hs_timestamp": "2026-05-02T10:00:00Z",
            "hubspot_owner_id": "owner-2",
            "hs_email_direction": "EMAIL",
            "hs_email_status": "SENT",
            "createdate": "2026-05-02T09:59:00Z",
            "hs_lastmodifieddate": "2026-05-02T10:05:00Z",
        },
        "meetings": {
            "hs_meeting_title": "Implementation sync",
            "hs_meeting_body": "Reviewed launch blockers.",
            "hs_meeting_start_time": "2026-05-03T10:00:00Z",
            "hubspot_owner_id": "owner-3",
            "hs_meeting_outcome": "COMPLETED",
            "createdate": "2026-05-03T09:59:00Z",
            "hs_lastmodifieddate": "2026-05-03T10:05:00Z",
        },
        "tasks": {
            "hs_task_subject": "Send migration plan",
            "hs_task_body": "Prepare the migration plan.",
            "hs_timestamp": "2026-05-04T10:00:00Z",
            "hubspot_owner_id": "owner-4",
            "hs_task_status": "WAITING",
            "createdate": "2026-05-04T09:59:00Z",
            "hs_lastmodifieddate": "2026-05-04T10:05:00Z",
        },
    }
    return {
        "id": activity_id,
        "archived": False,
        "createdAt": "2026-05-01T09:59:00Z",
        "updatedAt": "2026-05-01T10:05:00Z",
        "properties": props_by_type[activity_type],
        "associations": {"companies": {"results": [{"id": company_id, "type": f"{singular}_to_company"}]}},
        "url": f"https://hubspot.example/{activity_type}/{activity_id}",
    }


@pytest.mark.asyncio
async def test_hubspot_company_activities_fetches_associated_activities_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/crm/v4/objects/companies/company-1/associations/calls":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "toObjectId": "call-1",
                            "associationTypes": [{"typeId": 181, "label": "call_to_company"}],
                        }
                    ]
                },
            )
        return httpx.Response(200, json=_activity("call-1", "calls"))

    adapter = HubSpotCompanyActivitiesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={"company_ids": ["company-1"], "activity_types": ["call"], "association_type_id": 181},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert HubSpotCompanyActivityAdapter is HubSpotCompanyActivitiesAdapter
    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer hubspot-token"
    assert requests[0].headers["User-Agent"] == "max-hubspot-company-activities-import/1"
    assert requests[0].url.params["limit"] == "5"
    assert requests[1].url.path == "/crm/v3/objects/calls/call-1"
    assert "hs_call_title" in requests[1].url.params.get_list("properties")
    assert set(requests[1].url.params.get_list("associations")) == {"companies", "contacts", "deals"}

    signal = signals[0]
    assert signal.id == "hubspot-company-activity:company-1:call:call-1"
    assert signal.source_adapter == "hubspot_company_activities_import"
    assert signal.source_type.value == "market"
    assert signal.title == "Discovery call"
    assert signal.content == "Customer asked for rollout timing."
    assert signal.url == "https://hubspot.example/calls/call-1"
    assert signal.author == "owner-1"
    assert signal.metadata["company_id"] == "company-1"
    assert signal.metadata["activity_id"] == "call-1"
    assert signal.metadata["activity_type"] == "call"
    assert signal.metadata["owner_id"] == "owner-1"
    assert signal.metadata["subject"] == "Discovery call"
    assert signal.metadata["body"] == "Customer asked for rollout timing."
    assert signal.metadata["direction"] == "OUTBOUND"
    assert signal.metadata["status"] == "COMPLETED"
    assert signal.metadata["associations"]["companies"]["results"][0]["id"] == "company-1"
    assert signal.metadata["raw"]["id"] == "call-1"
    assert "hubspot" in signal.tags
    assert "call" in signal.tags


@pytest.mark.asyncio
async def test_hubspot_company_activities_filters_types_and_applies_page_limits() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/company-1/associations/emails") and request.url.params.get("after") is None:
            return httpx.Response(
                200,
                json={"results": [{"toObjectId": "email-1"}], "paging": {"next": {"after": "cursor-2"}}},
            )
        if request.url.path.endswith("/company-1/associations/emails"):
            return httpx.Response(200, json={"results": [{"toObjectId": "email-2"}]})
        if request.url.path.endswith("/company-2/associations/emails"):
            return httpx.Response(200, json={"results": [{"toObjectId": "email-3"}]})
        activity_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=_activity(activity_id, "emails"))

    adapter = HubSpotCompanyActivitiesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={
            "company_ids": ["company-1", "company-2"],
            "activity_types": ["emails"],
            "association_page_limit": 1,
            "per_company_limit": 2,
            "properties": {"emails": ["hs_email_subject", "hs_email_text", "hs_timestamp"]},
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    association_requests = [request for request in requests if "/associations/emails" in request.url.path]
    assert [request.url.params.get("after") for request in association_requests] == [None, "cursor-2", None]
    assert all("/associations/calls" not in request.url.path for request in requests)
    assert [signal.metadata["activity_id"] for signal in signals] == ["email-1", "email-2", "email-3"]
    assert [signal.metadata["company_id"] for signal in signals] == ["company-1", "company-1", "company-2"]
    fetch_requests = [request for request in requests if "/crm/v3/objects/emails/" in request.url.path]
    assert set(fetch_requests[0].url.params.get_list("properties")) == {
        "hs_email_subject",
        "hs_email_text",
        "hs_timestamp",
    }


@pytest.mark.asyncio
async def test_hubspot_company_activities_maps_meetings_and_tasks() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/associations/meetings"):
            return httpx.Response(200, json={"results": [{"toObjectId": "meeting-1"}]})
        if request.url.path.endswith("/associations/tasks"):
            return httpx.Response(200, json={"results": [{"toObjectId": "task-1"}]})
        activity_type = request.url.path.split("/")[-2]
        activity_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=_activity(activity_id, activity_type))

    adapter = HubSpotCompanyActivitiesAdapter(
        token="hubspot-token",
        config={"company_id": "company-1", "activity_types": "meeting,task"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=4)

    assert [signal.metadata["activity_type"] for signal in signals] == ["meeting", "task"]
    assert signals[0].title == "Implementation sync"
    assert signals[0].published_at is not None
    assert signals[1].title == "Send migration plan"
    assert signals[1].metadata["status"] == "WAITING"


@pytest.mark.asyncio
async def test_hubspot_company_activities_reads_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/associations/tasks"):
            return httpx.Response(200, json={"results": [{"toObjectId": "task-1"}]})
        return httpx.Response(200, json=_activity("task-1", "tasks"))

    adapter = HubSpotCompanyActivitiesAdapter(
        config={"company_ids": ["company-1"], "activity_type": "task"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert signals[0].metadata["activity_id"] == "task-1"


@pytest.mark.asyncio
async def test_hubspot_company_activities_empty_without_required_config_or_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotCompanyActivitiesAdapter(config={"company_ids": ["company-1"]}).fetch() == []
    assert await HubSpotCompanyActivitiesAdapter(token="token").fetch() == []
    assert await HubSpotCompanyActivitiesAdapter(token="token", config={"company_id": "company-1"}).fetch(limit=0) == []

    failing = HubSpotCompanyActivitiesAdapter(
        token="bad",
        config={"company_ids": ["company-1"], "activity_type": "call"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = HubSpotCompanyActivitiesAdapter(
        token="token",
        config={"company_ids": ["company-1"], "activity_type": "call"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=2) == []
