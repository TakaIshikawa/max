"""Tests for Salesforce Opportunity import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.salesforce_opportunities_adapter import SalesforceOpportunitiesAdapter


@pytest.mark.asyncio
async def test_salesforce_opportunities_builds_filtered_soql_and_maps_metadata() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "records": [
                    {
                        "Id": "006xx000001",
                        "Name": "Enterprise rollout",
                        "Description": "Expansion buying signal",
                        "AccountId": "001xx000001",
                        "Account": {"Name": "Acme"},
                        "Amount": 125000,
                        "StageName": "Negotiation",
                        "Probability": 80,
                        "OwnerId": "005xx000001",
                        "Owner": {"Name": "Ada"},
                        "CloseDate": "2026-06-30",
                        "CreatedDate": "2026-05-01T00:00:00.000+0000",
                        "LastModifiedDate": "2026-05-02T00:00:00.000+0000",
                        "IsClosed": False,
                    }
                ],
                "done": True,
            },
        )

    adapter = SalesforceOpportunitiesAdapter(
        {
            "stages": ["Negotiation", "Proposal"],
            "owner_ids": ["005xx000001"],
            "close_date_from": "2026-06-01",
            "close_date_to": "2026-06-30",
            "min_amount": 100000,
        },
        instance_url="https://example.my.salesforce.com",
        access_token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    query = requests[0].url.params["q"]
    assert "FROM Opportunity" in query
    assert "StageName IN ('Negotiation', 'Proposal')" in query
    assert "OwnerId IN ('005xx000001')" in query
    assert "CloseDate >= 2026-06-01" in query
    assert "CloseDate <= 2026-06-30" in query
    assert "Amount >= 100000" in query
    assert "IsClosed = false" in query
    assert requests[0].headers["Authorization"] == "Bearer token"
    assert signals[0].title == "Enterprise rollout"
    assert signals[0].url == "https://example.my.salesforce.com/lightning/r/Opportunity/006xx000001/view"
    assert "Account: Acme" in signals[0].content
    assert "Stage: Negotiation" in signals[0].content
    assert "Amount: 125000" in signals[0].content
    assert signals[0].metadata["salesforce_opportunity_id"] == "006xx000001"
    assert signals[0].metadata["account_id"] == "001xx000001"
    assert signals[0].metadata["account_name"] == "Acme"
    assert signals[0].metadata["stage_name"] == "Negotiation"
    assert signals[0].metadata["amount"] == 125000
    assert signals[0].metadata["probability"] == 80
    assert signals[0].metadata["owner_id"] == "005xx000001"
    assert signals[0].metadata["close_date"] == "2026-06-30"
    assert signals[0].metadata["created_at"] == "2026-05-01T00:00:00.000+0000"
    assert signals[0].metadata["updated_at"] == "2026-05-02T00:00:00.000+0000"


@pytest.mark.asyncio
async def test_salesforce_opportunities_follows_next_records_url_and_deduplicates() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/query"):
            return httpx.Response(
                200,
                json={
                    "records": [
                        {"Id": "0061", "Name": "One", "StageName": "Prospecting"},
                        {"Id": "0061", "Name": "One duplicate", "StageName": "Prospecting"},
                    ],
                    "nextRecordsUrl": "/services/data/v60.0/query/01g",
                },
            )
        return httpx.Response(200, json={"records": [{"Id": "0062", "Name": "Two", "StageName": "Proposal"}], "done": True})

    adapter = SalesforceOpportunitiesAdapter(
        instance_url="https://sf.test",
        access_token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["salesforce_opportunity_id"] for signal in signals] == ["0061", "0062"]
    assert paths == ["/services/data/v60.0/query", "/services/data/v60.0/query/01g"]


@pytest.mark.asyncio
async def test_salesforce_opportunities_include_closed_and_custom_fields() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"records": [], "done": True})

    adapter = SalesforceOpportunitiesAdapter(
        {"include_closed": True, "fields": ["Id", "Name", "Amount", "Probability"]},
        instance_url="https://sf.test",
        access_token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=1) == []
    query = requests[0].url.params["q"]
    assert query.startswith("SELECT Id, Name, Amount, Probability FROM Opportunity")
    assert "IsClosed = false" not in query


@pytest.mark.asyncio
async def test_salesforce_opportunities_returns_empty_without_credentials_or_positive_limit() -> None:
    adapter = SalesforceOpportunitiesAdapter(instance_url="", access_token="")

    assert await adapter.fetch(limit=5) == []

    adapter = SalesforceOpportunitiesAdapter(instance_url="https://sf.test", access_token="token")

    assert await adapter.fetch(limit=0) == []
