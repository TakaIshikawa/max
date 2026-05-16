"""Tests for Zendesk SLA policies import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.zendesk_sla_policies_adapter import (
    ZendeskSlaPoliciesAdapter,
    ZendeskSlaPoliciesImportAdapter,
)
from max.types.signal import SignalSourceType


POLICY = {
    "id": 123,
    "title": "Enterprise priority response",
    "active": True,
    "position": 1,
    "description": "Priority enterprise commitments",
    "filter": {
        "all": [{"field": "priority", "operator": "is", "value": "high"}],
        "any": [{"field": "organization_id", "operator": "is", "value": 42}],
    },
    "policy_metrics": [
        {
            "metric": "first_reply_time",
            "priority": "high",
            "target": {"value": 30, "unit": "minutes"},
            "business_hours": True,
        }
    ],
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-02T11:00:00Z",
    "url": "https://acme.zendesk.com/api/v2/slas/policies/123.json",
}


@pytest.mark.asyncio
async def test_zendesk_sla_policies_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "sla_policies": [POLICY],
                    "next_page": "https://acme.zendesk.com/api/v2/slas/policies.json?page=2",
                },
            )
        return httpx.Response(
            200,
            json={"sla_policies": [{**POLICY, "id": 124, "title": "Standard response", "active": False}], "next_page": None},
        )

    adapter = ZendeskSlaPoliciesAdapter(
        api_url="https://acme.zendesk.com",
        email="agent@example.com",
        token="zd-token",
        config={"page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert ZendeskSlaPoliciesAdapter is ZendeskSlaPoliciesImportAdapter
    assert len(requests) == 2
    assert requests[0].url.path == "/api/v2/slas/policies.json"
    assert requests[0].url.params["per_page"] == "1"
    expected_auth = base64.b64encode(b"agent@example.com/token:zd-token").decode()
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["policy_id"] for signal in signals] == [123, 124]

    signal = signals[0]
    assert signal.id == "zendesk-sla-policy:123"
    assert signal.source_type == SignalSourceType.MARKET
    assert signal.source_adapter == "zendesk_sla_policies_import"
    assert signal.title == "Enterprise priority response"
    assert "commitments first_reply_time high 30" in signal.content
    assert "filters all:priority is high" in signal.content
    assert signal.metadata["active"] is True
    assert signal.metadata["description"] == "Priority enterprise commitments"
    assert signal.metadata["filter_summary"] == [
        "all:priority is high",
        "any:organization_id is 42",
    ]
    assert signal.metadata["policy_metrics"] == [
        {
            "metric": "first_reply_time",
            "priority": "high",
            "target": {"value": 30, "unit": "minutes"},
            "business_hours": True,
            "target_minutes": 30,
            "target_unit": "minutes",
        }
    ]
    assert signal.metadata["updated_at"] == "2026-05-02T11:00:00Z"
    assert signal.metadata["raw"] == POLICY


@pytest.mark.asyncio
async def test_zendesk_sla_policies_supports_cursor_pagination_and_truncates() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"sla_policies": [POLICY], "meta": {"has_more": True, "after_cursor": "abc"}})
        return httpx.Response(200, json={"sla_policies": [{**POLICY, "id": 125}], "meta": {"has_more": False}})

    adapter = ZendeskSlaPoliciesAdapter(
        config={"subdomain": "acme", "email": "agent@example.com", "api_token": "zd-token", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.host == "acme.zendesk.com"
    assert requests[1].url.params["page[after]"] == "abc"
    assert [signal.metadata["policy_id"] for signal in signals] == [123, 125]

    truncating = ZendeskSlaPoliciesAdapter(
        config={"subdomain": "acme", "email": "agent@example.com", "api_token": "zd-token", "page_size": 2},
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"sla_policies": [POLICY, {**POLICY, "id": 126}]})
            )
        ),
    )

    assert [signal.metadata["policy_id"] for signal in await truncating.fetch(limit=1)] == [123]


@pytest.mark.asyncio
async def test_zendesk_sla_policies_empty_without_required_config_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZENDESK_API_URL", raising=False)
    monkeypatch.delenv("ZENDESK_BASE_URL", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    monkeypatch.delenv("ZENDESK_EMAIL", raising=False)
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)

    assert await ZendeskSlaPoliciesAdapter().fetch() == []
    assert await ZendeskSlaPoliciesAdapter(api_url="https://max.zendesk.com", email="agent@example.com", token="token").fetch(limit=0) == []

    failing = ZendeskSlaPoliciesAdapter(
        api_url="https://max.zendesk.com",
        email="agent@example.com",
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    malformed = ZendeskSlaPoliciesAdapter(
        api_url="https://max.zendesk.com",
        email="agent@example.com",
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))),
    )

    assert await failing.fetch(limit=2) == []
    assert await malformed.fetch(limit=2) == []
