"""Tests for Salesforce Lead import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.salesforce_leads_adapter import SalesforceLeadAdapter, SalesforceLeadsAdapter


@pytest.mark.asyncio
async def test_salesforce_leads_builds_filtered_soql_and_maps_metadata() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"records": [_lead()], "done": True})

    adapter = SalesforceLeadsAdapter(
        {
            "statuses": ["Open - Not Contacted", "Working"],
            "lead_sources": ["Web"],
            "owner_ids": ["005xx000001"],
            "industries": ["Technology"],
            "ratings": ["Hot"],
            "created_after": "2026-05-01T00:00:00Z",
        },
        instance_url="https://example.my.salesforce.com",
        access_token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert SalesforceLeadAdapter is SalesforceLeadsAdapter
    query = requests[0].url.params["q"]
    assert "FROM Lead" in query
    assert "Status IN ('Open - Not Contacted', 'Working')" in query
    assert "LeadSource IN ('Web')" in query
    assert "OwnerId IN ('005xx000001')" in query
    assert "Industry IN ('Technology')" in query
    assert "Rating IN ('Hot')" in query
    assert "CreatedDate >= 2026-05-01T00:00:00Z" in query
    assert "IsConverted = false" in query
    assert requests[0].headers["Authorization"] == "Bearer token"
    assert signals[0].id == "salesforce-lead:00Qxx000001"
    assert signals[0].title == "Ada Lovelace"
    assert signals[0].url == "https://example.my.salesforce.com/lightning/r/Lead/00Qxx000001/view"
    assert signals[0].author == "Grace Hopper"
    assert signals[0].published_at is not None
    assert "Company: Acme" in signals[0].content
    assert "Status: Open - Not Contacted" in signals[0].content
    assert "Lead source: Web" in signals[0].content
    assert "Industry: Technology" in signals[0].content
    assert "Rating: Hot" in signals[0].content
    assert signals[0].metadata["salesforce_lead_id"] == "00Qxx000001"
    assert signals[0].metadata["company"] == "Acme"
    assert signals[0].metadata["status"] == "Open - Not Contacted"
    assert signals[0].metadata["lead_source"] == "Web"
    assert signals[0].metadata["owner_id"] == "005xx000001"
    assert signals[0].metadata["owner_name"] == "Grace Hopper"
    assert signals[0].metadata["industry"] == "Technology"
    assert signals[0].metadata["rating"] == "Hot"
    assert signals[0].metadata["created_at"] == "2026-05-01T00:00:00.000+0000"
    assert signals[0].metadata["updated_at"] == "2026-05-02T00:00:00.000+0000"
    assert "lead" in signals[0].tags


@pytest.mark.asyncio
async def test_salesforce_leads_follows_next_records_url_and_deduplicates() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/query"):
            return httpx.Response(
                200,
                json={
                    "records": [
                        {"Id": "00Q1", "Name": "One", "Company": "Acme", "Status": "Working"},
                        {"Id": "00Q1", "Name": "Duplicate", "Company": "Acme", "Status": "Working"},
                    ],
                    "nextRecordsUrl": "/services/data/v60.0/query/01g",
                },
            )
        return httpx.Response(
            200,
            json={"records": [{"Id": "00Q2", "Name": "Two", "Company": "Globex"}], "done": True},
        )

    adapter = SalesforceLeadsAdapter(
        instance_url="https://sf.test",
        access_token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["salesforce_lead_id"] for signal in signals] == ["00Q1", "00Q2"]
    assert paths == ["/services/data/v60.0/query", "/services/data/v60.0/query/01g"]


@pytest.mark.asyncio
async def test_salesforce_leads_include_converted_and_custom_fields() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"records": [], "done": True})

    adapter = SalesforceLeadsAdapter(
        {"include_converted": True, "fields": ["Id", "Name", "Company", "Status"]},
        instance_url="https://sf.test",
        access_token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=1) == []
    query = requests[0].url.params["q"]
    assert query.startswith("SELECT Id, Name, Company, Status FROM Lead")
    assert "IsConverted = false" not in query


@pytest.mark.asyncio
async def test_salesforce_leads_missing_credentials_non_positive_limit_and_api_failure_return_empty() -> None:
    assert await SalesforceLeadsAdapter(instance_url="", access_token="").fetch(limit=5) == []
    assert await SalesforceLeadsAdapter(instance_url="https://sf.test", access_token="token").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = SalesforceLeadsAdapter(
        instance_url="https://sf.test",
        access_token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch(limit=1) == []


def _lead() -> dict:
    return {
        "Id": "00Qxx000001",
        "Name": "Ada Lovelace",
        "FirstName": "Ada",
        "LastName": "Lovelace",
        "Company": "Acme",
        "Title": "CTO",
        "Description": "Evaluating the platform",
        "Status": "Open - Not Contacted",
        "LeadSource": "Web",
        "OwnerId": "005xx000001",
        "Owner": {"Name": "Grace Hopper"},
        "Industry": "Technology",
        "Rating": "Hot",
        "Email": "ada@example.com",
        "CreatedDate": "2026-05-01T00:00:00.000+0000",
        "LastModifiedDate": "2026-05-02T00:00:00.000+0000",
        "IsConverted": False,
    }
