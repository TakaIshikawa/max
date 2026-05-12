"""Tests for Salesforce Case import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.salesforce_cases_adapter import SalesforceCasesAdapter


@pytest.mark.asyncio
async def test_salesforce_cases_fetch_maps_case() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "records": [
                    {
                        "Id": "500xx000001",
                        "CaseNumber": "00001042",
                        "Subject": "Login failure",
                        "Description": "Customer cannot sign in",
                        "Status": "New",
                        "Priority": "High",
                        "Origin": "Email",
                        "Account": {"Name": "Acme"},
                        "Contact": {"Name": "Grace"},
                        "Owner": {"Name": "Ada"},
                        "CreatedDate": "2026-05-01T00:00:00.000+0000",
                        "LastModifiedDate": "2026-05-02T00:00:00.000+0000",
                    }
                ],
                "done": True,
            },
        )

    adapter = SalesforceCasesAdapter(instance_url="https://example.my.salesforce.com", access_token="token", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=5)

    assert requests[0].headers["Authorization"] == "Bearer token"
    assert "SELECT" in requests[0].url.params["q"]
    assert signals[0].title == "Login failure"
    assert signals[0].url == "https://example.my.salesforce.com/lightning/r/Case/500xx000001/view"
    assert signals[0].metadata["case_number"] == "00001042"
    assert signals[0].metadata["status"] == "New"
    assert signals[0].metadata["priority"] == "High"
    assert signals[0].metadata["origin"] == "Email"
    assert signals[0].metadata["account"] == "Acme"
    assert signals[0].metadata["contact"] == "Grace"
    assert signals[0].metadata["owner"] == "Ada"


@pytest.mark.asyncio
async def test_salesforce_cases_follows_next_records_url() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/query"):
            return httpx.Response(200, json={"records": [{"Id": "5001", "CaseNumber": "1", "Subject": "One"}], "nextRecordsUrl": "/services/data/v60.0/query/01g"})
        return httpx.Response(200, json={"records": [{"Id": "5002", "CaseNumber": "2", "Subject": "Two"}], "done": True})

    adapter = SalesforceCasesAdapter(instance_url="https://sf.test", access_token="token", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["salesforce_case_id"] for signal in signals] == ["5001", "5002"]
    assert paths == ["/services/data/v60.0/query", "/services/data/v60.0/query/01g"]


@pytest.mark.asyncio
async def test_salesforce_cases_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = SalesforceCasesAdapter(instance_url="https://sf.test", access_token="token", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch() == []
