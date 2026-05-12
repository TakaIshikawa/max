"""Tests for HubSpot company notes import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_company_notes_adapter import (
    HubSpotCompanyNoteAdapter,
    HubSpotCompanyNotesAdapter,
)


def _note(note_id: str, *, body: str | None = None, created_at: str = "2026-05-01T10:00:00Z") -> dict:
    return {
        "id": note_id,
        "archived": False,
        "createdAt": created_at,
        "updatedAt": "2026-05-02T10:00:00Z",
        "properties": {
            "hs_note_body": body or f"Company note {note_id}",
            "hs_timestamp": created_at,
            "hubspot_owner_id": "owner-1",
            "createdate": created_at,
            "hs_lastmodifieddate": "2026-05-02T10:00:00Z",
        },
    }


@pytest.mark.asyncio
async def test_hubspot_company_notes_fetches_associated_notes_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/crm/v4/objects/companies/company-1/associations/notes":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "toObjectId": "note-1",
                            "associationTypes": [
                                {"typeId": 190, "category": "HUBSPOT_DEFINED", "label": "note_to_company"}
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(200, json=_note("note-1", body="Customer asked for SSO."))

    adapter = HubSpotCompanyNotesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={"company_ids": ["company-1"], "association_type_id": 190},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert HubSpotCompanyNoteAdapter is HubSpotCompanyNotesAdapter
    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer hubspot-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[0].url.params["limit"] == "5"
    assert requests[1].url.path == "/crm/v3/objects/notes/note-1"
    assert set(requests[1].url.params.get_list("properties")) >= {
        "hs_note_body",
        "hs_timestamp",
        "hubspot_owner_id",
        "createdate",
        "hs_lastmodifieddate",
    }

    signal = signals[0]
    assert signal.id == "hubspot-company-note:company-1:note-1"
    assert signal.source_adapter == "hubspot_company_notes_import"
    assert signal.source_type.value == "market"
    assert signal.title == "HubSpot company company-1 note"
    assert signal.content == "Customer asked for SSO."
    assert signal.author == "owner-1"
    assert signal.published_at is not None
    assert signal.metadata["signal_role"] == "customer"
    assert signal.metadata["company_id"] == "company-1"
    assert signal.metadata["note_id"] == "note-1"
    assert signal.metadata["body"] == "Customer asked for SSO."
    assert "hubspot" in signal.tags
    assert "note" in signal.tags


@pytest.mark.asyncio
async def test_hubspot_company_notes_paginates_companies_and_applies_limits() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/company-1/associations/notes") and request.url.params.get("after") is None:
            return httpx.Response(
                200,
                json={
                    "results": [{"toObjectId": "note-1"}],
                    "paging": {"next": {"after": "cursor-2"}},
                },
            )
        if request.url.path.endswith("/company-1/associations/notes"):
            return httpx.Response(200, json={"results": [{"toObjectId": "note-2"}]})
        if request.url.path.endswith("/company-2/associations/notes"):
            return httpx.Response(200, json={"results": [{"toObjectId": "note-3"}]})
        note_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=_note(note_id))

    adapter = HubSpotCompanyNotesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={"company_ids": ["company-1", "company-2"], "per_company_limit": 2, "association_page_limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    association_requests = [request for request in requests if "/associations/notes" in request.url.path]
    assert [request.url.params.get("after") for request in association_requests] == [None, "cursor-2", None]
    assert [signal.metadata["note_id"] for signal in signals] == ["note-1", "note-2", "note-3"]
    assert [signal.metadata["company_id"] for signal in signals] == ["company-1", "company-1", "company-2"]


@pytest.mark.asyncio
async def test_hubspot_company_notes_filters_created_after_and_association_type() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/associations/notes"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"toObjectId": "note-old", "associationTypes": [{"typeId": 190}]},
                        {"toObjectId": "note-new", "associationTypes": [{"typeId": 190}]},
                        {"toObjectId": "note-skipped", "associationTypes": [{"typeId": 999}]},
                    ]
                },
            )
        note_id = request.url.path.rsplit("/", 1)[-1]
        created_at = "2026-04-01T00:00:00Z" if note_id == "note-old" else "2026-05-10T00:00:00Z"
        return httpx.Response(200, json=_note(note_id, created_at=created_at))

    adapter = HubSpotCompanyNotesAdapter(
        token="hubspot-token",
        config={
            "company_id": "company-1",
            "association_type_ids": ["190"],
            "created_after": "2026-05-01T00:00:00Z",
            "properties": ["hs_note_body", "createdate"],
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    fetched_note_paths = [request.url.path for request in requests if "/crm/v3/objects/notes/" in request.url.path]
    assert fetched_note_paths == ["/crm/v3/objects/notes/note-old", "/crm/v3/objects/notes/note-new"]
    assert [signal.metadata["note_id"] for signal in signals] == ["note-new"]


@pytest.mark.asyncio
async def test_hubspot_company_notes_reads_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUBSPOT_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/associations/notes"):
            return httpx.Response(200, json={"results": [{"toObjectId": "note-1"}]})
        return httpx.Response(200, json=_note("note-1"))

    adapter = HubSpotCompanyNotesAdapter(
        config={"company_ids": ["company-1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert signals[0].metadata["note_id"] == "note-1"


@pytest.mark.asyncio
async def test_hubspot_company_notes_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotCompanyNotesAdapter(config={"company_ids": ["company-1"]}).fetch() == []
    assert await HubSpotCompanyNotesAdapter(token="token").fetch() == []
    assert await HubSpotCompanyNotesAdapter(token="token", config={"company_ids": ["company-1"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_hubspot_company_notes_http_or_non_json_failure_returns_empty() -> None:
    failing = HubSpotCompanyNotesAdapter(
        token="bad",
        config={"company_ids": ["company-1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = HubSpotCompanyNotesAdapter(
        token="token",
        config={"company_ids": ["company-1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=2) == []
