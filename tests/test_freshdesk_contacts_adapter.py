"""Tests for Freshdesk contacts import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.freshdesk_contacts_adapter import FreshdeskContactsAdapter, FreshdeskContactsImportAdapter


def _contact(number: int, **overrides: object) -> dict:
    contact = {
        "id": 7000 + number,
        "name": f"Customer {number}",
        "email": f"customer{number}@example.com",
        "phone": f"+1555000{number}",
        "company_id": 8000 + number,
        "active": True,
        "deleted": False,
        "tags": ["vip", f"tier-{number}"],
        "created_at": f"2026-05-0{number}T10:00:00Z",
        "updated_at": f"2026-05-0{number}T11:00:00Z",
    }
    contact.update(overrides)
    return contact


@pytest.mark.asyncio
async def test_freshdesk_contacts_uses_config_auth_and_maps_identity_fields() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_contact(1)])

    adapter = FreshdeskContactsImportAdapter(
        config={"domain": "acme", "api_key": "freshdesk-key", "updated_since": "2026-05-01T00:00:00Z"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert FreshdeskContactsAdapter is FreshdeskContactsImportAdapter
    assert adapter.domain == "acme.freshdesk.com"
    assert requests[0].url.path == "/api/v2/contacts"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].url.params["updated_since"] == "2026-05-01T00:00:00Z"
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert len(signals) == 1
    assert signals[0].id == "freshdesk-contact:7001"
    assert signals[0].source_adapter == "freshdesk_contacts_import"
    assert signals[0].source_type.value == "roadmap"
    assert signals[0].title == "Customer 1"
    assert signals[0].url == "https://acme.freshdesk.com/a/contacts/7001"
    assert signals[0].author == "customer1@example.com"
    assert signals[0].metadata["contact_id"] == 7001
    assert signals[0].metadata["name"] == "Customer 1"
    assert signals[0].metadata["email"] == "customer1@example.com"
    assert signals[0].metadata["phone"] == "+15550001"
    assert signals[0].metadata["company_id"] == 8001
    assert signals[0].metadata["active"] is True
    assert signals[0].metadata["deleted"] is False
    assert signals[0].metadata["tags"] == ["vip", "tier-1"]
    assert signals[0].metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signals[0].metadata["updated_at"] == "2026-05-01T11:00:00Z"


@pytest.mark.asyncio
async def test_freshdesk_contacts_follows_link_header_and_total_limit() -> None:
    requested_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if len(requested_urls) == 1:
            return httpx.Response(
                200,
                json=[_contact(1)],
                headers={"Link": '<https://acme.freshdesk.com/api/v2/contacts?page=2>; rel="next"'},
            )
        return httpx.Response(200, json=[_contact(2)])

    adapter = FreshdeskContactsImportAdapter(
        domain="acme.freshdesk.com",
        api_key="freshdesk-key",
        config={"page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requested_urls) == 2
    assert [signal.metadata["contact_id"] for signal in signals] == [7001, 7002]


@pytest.mark.asyncio
async def test_freshdesk_contacts_page_params_and_missing_optional_fields() -> None:
    requested_pages: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_pages.append(request.url.params.get("page", ""))
        if request.url.params.get("page") == "1":
            return httpx.Response(200, json=[_contact(1)])
        return httpx.Response(
            200,
            json=[
                _contact(
                    2,
                    name="",
                    email="",
                    phone="",
                    mobile="+15559999",
                    company_id=None,
                    active=None,
                    deleted=None,
                    tags=None,
                )
            ],
        )

    adapter = FreshdeskContactsImportAdapter(
        domain="acme",
        api_key="freshdesk-key",
        config={"page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert requested_pages == ["1", "2"]
    assert len(signals) == 2
    assert signals[1].title == "Freshdesk contact 7002"
    assert signals[1].author is None
    assert signals[1].metadata["phone"] == "+15559999"
    assert signals[1].metadata["company_id"] is None
    assert signals[1].metadata["active"] is None
    assert signals[1].metadata["deleted"] is None
    assert signals[1].metadata["tags"] == []


@pytest.mark.asyncio
async def test_freshdesk_contacts_empty_without_config_env_or_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRESHDESK_DOMAIN", raising=False)
    monkeypatch.delenv("FRESHDESK_API_KEY", raising=False)

    assert await FreshdeskContactsImportAdapter().fetch() == []
    assert await FreshdeskContactsImportAdapter(domain="acme", api_key="key").fetch(limit=0) == []

    failing = FreshdeskContactsImportAdapter(
        domain="acme",
        api_key="key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )

    assert await failing.fetch(limit=2) == []
