"""Tests for Salesforce CaseComment import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.salesforce_case_comments_adapter import SalesforceCaseCommentsAdapter
from max.types.signal import SignalSourceType


def _comment(number: int, *, case_id: str = "500xx000001") -> dict:
    return {
        "Id": f"00a{number}",
        "ParentId": case_id,
        "CommentBody": f"Customer comment {number}",
        "IsPublished": True,
        "CreatedById": "005xx000001",
        "CreatedBy": {"Name": "Ada Lovelace"},
        "CreatedDate": "2026-05-01T00:00:00.000+0000",
        "LastModifiedDate": "2026-05-02T00:00:00.000+0000",
    }


@pytest.mark.asyncio
async def test_salesforce_case_comments_queries_case_comments_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"records": [_comment(1)], "done": True})

    adapter = SalesforceCaseCommentsAdapter(
        instance_url="https://example.my.salesforce.com",
        access_token="token",
        config={"case_ids": ["500xx000001"], "api_version": "v61.0", "page_size": 50},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requests[0].url.path == "/services/data/v61.0/query"
    query = requests[0].url.params["q"]
    assert "FROM CaseComment" in query
    assert "ParentId IN ('500xx000001')" in query
    assert requests[0].headers["Authorization"] == "Bearer token"
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[0].headers["Sforce-Query-Options"] == "batchSize=50"
    signal = signals[0]
    assert signal.id == "salesforce-case-comment:00a1"
    assert signal.source_type == SignalSourceType.SURVEY
    assert signal.source_adapter == "salesforce_case_comments_import"
    assert signal.title == "Salesforce case comment 00a1"
    assert signal.content == "Customer comment 1"
    assert signal.url == "https://example.my.salesforce.com/lightning/r/Case/500xx000001/view"
    assert signal.author == "Ada Lovelace"
    assert signal.metadata["salesforce_case_comment_id"] == "00a1"
    assert signal.metadata["salesforce_case_id"] == "500xx000001"
    assert signal.metadata["comment_body"] == "Customer comment 1"
    assert signal.metadata["is_published"] is True
    assert signal.metadata["created_by"] == "Ada Lovelace"


@pytest.mark.asyncio
async def test_salesforce_case_comments_follows_next_records_url_and_deduplicates() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/query"):
            return httpx.Response(
                200,
                json={
                    "records": [_comment(1), _comment(1)],
                    "nextRecordsUrl": "/services/data/v60.0/query/01g",
                },
            )
        return httpx.Response(200, json={"records": [_comment(2)], "done": True})

    adapter = SalesforceCaseCommentsAdapter(
        instance_url="https://sf.test",
        access_token="token",
        config={"case_ids": ["5001"], "limit": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert [signal.metadata["salesforce_case_comment_id"] for signal in signals] == ["00a1", "00a2"]
    assert paths == ["/services/data/v60.0/query", "/services/data/v60.0/query/01g"]


@pytest.mark.asyncio
async def test_salesforce_case_comments_empty_without_required_config_or_positive_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SALESFORCE_INSTANCE_URL", raising=False)
    monkeypatch.delenv("SALESFORCE_ACCESS_TOKEN", raising=False)

    assert await SalesforceCaseCommentsAdapter(access_token="token", config={"case_ids": ["5001"]}).fetch() == []
    assert await SalesforceCaseCommentsAdapter(instance_url="https://sf.test", config={"case_ids": ["5001"]}).fetch() == []
    assert await SalesforceCaseCommentsAdapter(instance_url="https://sf.test", access_token="token").fetch() == []
    assert await SalesforceCaseCommentsAdapter(instance_url="https://sf.test", access_token="token", config={"case_id": "5001"}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_salesforce_case_comments_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = SalesforceCaseCommentsAdapter(
        instance_url="https://sf.test",
        access_token="token",
        config={"case_ids": ["5001"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=5) == []
