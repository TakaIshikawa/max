"""Tests for Salesforce Campaign import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.salesforce_campaigns_adapter import SalesforceCampaignsAdapter


def _campaign(number: int, **overrides: object) -> dict:
    campaign = {
        "Id": f"701xx00000{number}",
        "Name": f"Launch campaign {number}",
        "Type": "Webinar",
        "Status": "In Progress",
        "Description": f"Campaign description {number}",
        "BudgetedCost": 1000.0,
        "ActualCost": 250.0,
        "ExpectedRevenue": 5000.0,
        "ExpectedResponse": 12.5,
        "StartDate": "2026-05-01",
        "EndDate": "2026-05-31",
        "ParentId": "701parent",
        "Parent": {"Name": "Parent campaign"},
        "OwnerId": "005owner",
        "Owner": {"Name": "Ada Lovelace"},
        "CreatedDate": "2026-05-01T00:00:00.000+0000",
        "LastModifiedDate": "2026-05-02T00:00:00.000+0000",
        "IsActive": True,
    }
    campaign.update(overrides)
    return campaign


@pytest.mark.asyncio
async def test_salesforce_campaigns_queries_campaigns_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"records": [_campaign(1)], "done": True})

    adapter = SalesforceCampaignsAdapter(
        instance_url="https://example.my.salesforce.com",
        access_token="token",
        config={"api_version": "v61.0", "page_size": 50, "statuses": ["In Progress"], "active_only": True},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requests[0].url.path == "/services/data/v61.0/query"
    query = requests[0].url.params["q"]
    assert "FROM Campaign" in query
    assert "Status IN ('In Progress')" in query
    assert "IsActive = true" in query
    assert requests[0].headers["Authorization"] == "Bearer token"
    assert requests[0].headers["Sforce-Query-Options"] == "batchSize=50"

    signal = signals[0]
    assert signal.id == "salesforce-campaign:701xx000001"
    assert signal.source_adapter == "salesforce_campaigns_import"
    assert signal.title == "Launch campaign 1"
    assert "Budgeted cost: 1000.0" in signal.content
    assert "Expected revenue: 5000.0" in signal.content
    assert "Parent campaign: Parent campaign" in signal.content
    assert signal.author == "Ada Lovelace"
    assert signal.metadata["salesforce_campaign_id"] == "701xx000001"
    assert signal.metadata["type"] == "Webinar"
    assert signal.metadata["status"] == "In Progress"
    assert signal.metadata["budgeted_cost"] == 1000.0
    assert signal.metadata["expected_revenue"] == 5000.0
    assert signal.metadata["start_date"] == "2026-05-01"
    assert signal.metadata["end_date"] == "2026-05-31"
    assert signal.metadata["parent_name"] == "Parent campaign"
    assert signal.metadata["raw"] == _campaign(1)


@pytest.mark.asyncio
async def test_salesforce_campaigns_follows_next_records_url_and_optional_financial_fields() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/query"):
            return httpx.Response(
                200,
                json={"records": [_campaign(1), _campaign(1)], "nextRecordsUrl": "/services/data/v60.0/query/01g"},
            )
        return httpx.Response(200, json={"records": [_campaign(2, BudgetedCost=None, ExpectedRevenue=None, Parent=None, ParentId=None)], "done": True})

    adapter = SalesforceCampaignsAdapter(
        instance_url="https://sf.test",
        access_token="token",
        config={"limit": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert [signal.metadata["salesforce_campaign_id"] for signal in signals] == ["701xx000001", "701xx000002"]
    assert paths == ["/services/data/v60.0/query", "/services/data/v60.0/query/01g"]
    assert signals[1].metadata["budgeted_cost"] is None
    assert signals[1].metadata["expected_revenue"] is None
    assert signals[1].metadata["parent_name"] is None


@pytest.mark.asyncio
async def test_salesforce_campaigns_empty_and_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SALESFORCE_INSTANCE_URL", raising=False)
    monkeypatch.delenv("SALESFORCE_ACCESS_TOKEN", raising=False)

    assert await SalesforceCampaignsAdapter(access_token="token").fetch() == []
    assert await SalesforceCampaignsAdapter(instance_url="https://sf.test").fetch() == []
    assert await SalesforceCampaignsAdapter(instance_url="https://sf.test", access_token="token").fetch(limit=0) == []

    empty = SalesforceCampaignsAdapter(
        instance_url="https://sf.test",
        access_token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"records": []}))),
    )
    assert await empty.fetch(limit=5) == []

    failing = SalesforceCampaignsAdapter(
        instance_url="https://sf.test",
        access_token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=5) == []
