from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.freshservice_tickets_adapter import FreshserviceTicketsAdapter


@pytest.mark.asyncio
async def test_fetches_tickets_with_basic_auth_filters_and_maps_metadata() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "tickets": [
                    {
                        "id": 42,
                        "display_id": 10042,
                        "subject": "Provisioning blocks rollout",
                        "description_text": "Admins cannot provision pilot users.",
                        "requester_id": 7,
                        "responder_id": 8,
                        "department_id": 9,
                        "category": "Access",
                        "sub_category": "SSO",
                        "item_category": "SAML",
                        "priority": 3,
                        "status": 2,
                        "source": 1,
                        "created_at": "2026-05-01T10:00:00Z",
                        "updated_at": "2026-05-02T10:00:00Z",
                        "due_by": "2026-05-03T10:00:00Z",
                        "custom_fields": {"cf_impact": "enterprise"},
                    }
                ]
            },
        )

    adapter = FreshserviceTicketsAdapter(
        domain="acme",
        api_key="fresh-key",
        status=2,
        requester_id=7,
        department_id=9,
        page_size=25,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    expected_auth = base64.b64encode(b"fresh-key:X").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[0].url == (
        "https://acme.freshservice.com/api/v2/tickets?"
        "page=1&per_page=10&status=2&requester_id=7&department_id=9"
    )
    assert len(signals) == 1
    assert signals[0].source_adapter == "freshservice_tickets_import"
    assert signals[0].title == "Provisioning blocks rollout"
    assert signals[0].content == "Admins cannot provision pilot users."
    assert signals[0].url == "https://acme.freshservice.com/a/tickets/10042"
    assert signals[0].metadata["freshservice_ticket_id"] == 42
    assert signals[0].metadata["display_id"] == 10042
    assert signals[0].metadata["requester_id"] == 7
    assert signals[0].metadata["responder_id"] == 8
    assert signals[0].metadata["department_id"] == 9
    assert signals[0].metadata["category"] == "Access"
    assert signals[0].metadata["sub_category"] == "SSO"
    assert signals[0].metadata["item_category"] == "SAML"
    assert signals[0].metadata["priority"] == 3
    assert signals[0].metadata["status"] == 2
    assert signals[0].metadata["source"] == 1
    assert signals[0].metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signals[0].metadata["updated_at"] == "2026-05-02T10:00:00Z"
    assert signals[0].metadata["due_by"] == "2026-05-03T10:00:00Z"
    assert signals[0].metadata["custom_fields"] == {"cf_impact": "enterprise"}
    assert "freshservice" in signals[0].tags


@pytest.mark.asyncio
async def test_paginates_deduplicates_and_stops_at_limit_without_extra_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["page"] == "1":
            return httpx.Response(
                200,
                json={"tickets": [{"id": 1, "subject": "One"}, {"id": 1, "subject": "Dupe"}]},
            )
        return httpx.Response(200, json={"tickets": [{"id": 2, "subject": "Two"}]})

    adapter = FreshserviceTicketsAdapter(
        domain="acme",
        api_key="fresh-key",
        page_size=2,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["freshservice_ticket_id"] for signal in signals] == [1, 2]
    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert [request.url.params["per_page"] for request in requests] == ["2", "1"]


@pytest.mark.asyncio
async def test_limit_smaller_than_page_size_fetches_only_needed_page_size() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"tickets": [{"id": 1, "subject": "One"}, {"id": 2, "subject": "Two"}]},
        )

    adapter = FreshserviceTicketsAdapter(
        domain="acme",
        api_key="fresh-key",
        page_size=100,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert [signal.title for signal in signals] == ["One"]
    assert len(requests) == 1
    assert requests[0].url.params["per_page"] == "1"


@pytest.mark.asyncio
async def test_missing_credentials_limit_and_http_failure_return_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FRESHSERVICE_DOMAIN", raising=False)
    monkeypatch.delenv("FRESHSERVICE_API_KEY", raising=False)
    assert await FreshserviceTicketsAdapter().fetch() == []
    assert await FreshserviceTicketsAdapter(domain="acme", api_key="key").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    adapter = FreshserviceTicketsAdapter(
        domain="acme",
        api_key="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch() == []


def test_resolves_credentials_and_overrides_from_config_and_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRESHSERVICE_DOMAIN", "env-domain")
    monkeypatch.setenv("FRESHSERVICE_API_KEY", "env-key")

    env_adapter = FreshserviceTicketsAdapter()
    assert env_adapter.domain == "env-domain"
    assert env_adapter.api_key == "env-key"
    assert env_adapter.api_url == "https://env-domain.freshservice.com"

    config_adapter = FreshserviceTicketsAdapter(
        config={
            "domain": "config-domain",
            "api_key": "config-key",
            "api_url": "https://fresh.example.test",
            "page_size": 250,
        }
    )
    assert config_adapter.domain == "config-domain"
    assert config_adapter.api_key == "config-key"
    assert config_adapter.api_url == "https://fresh.example.test"
    assert config_adapter.page_size == 100
