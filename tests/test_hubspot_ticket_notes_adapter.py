"""Tests for HubSpot ticket notes import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_ticket_notes_adapter import HubSpotTicketNoteAdapter, HubSpotTicketNotesAdapter


def _note(
    note_id: str,
    *,
    body: str | None = None,
    archived: bool = False,
    created_at: str = "2026-05-01T10:00:00Z",
    include_optional: bool = True,
) -> dict:
    note = {
        "id": note_id,
        "archived": archived,
        "createdAt": created_at,
        "updatedAt": "2026-05-02T10:00:00Z",
        "properties": {
            "hs_note_body": body or f"Ticket note {note_id}",
            "hs_timestamp": created_at,
            "createdate": created_at,
        },
    }
    if include_optional:
        note["properties"]["hubspot_owner_id"] = "owner-1"
        note["properties"]["hs_lastmodifieddate"] = "2026-05-02T10:00:00Z"
    return note


@pytest.mark.asyncio
async def test_hubspot_ticket_notes_fetches_associated_notes_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/crm/v4/objects/tickets/ticket-1/associations/notes":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "toObjectId": "note-1",
                            "associationTypes": [
                                {"typeId": 228, "category": "HUBSPOT_DEFINED", "label": "note_to_ticket"}
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(200, json=_note("note-1", body="Customer supplied reproduction details."))

    adapter = HubSpotTicketNotesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={"ticket_ids": ["ticket-1"], "association_type_id": 228},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert HubSpotTicketNoteAdapter is HubSpotTicketNotesAdapter
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
    assert signal.id == "hubspot-ticket-note:ticket-1:note-1"
    assert signal.source_adapter == "hubspot_ticket_notes_import"
    assert signal.source_type.value == "market"
    assert signal.title == "HubSpot ticket ticket-1 note"
    assert signal.content == "Customer supplied reproduction details."
    assert signal.author == "owner-1"
    assert signal.metadata["signal_role"] == "sales"
    assert signal.metadata["ticket_id"] == "ticket-1"
    assert signal.metadata["note_id"] == "note-1"
    assert signal.metadata["body"] == "Customer supplied reproduction details."
    assert signal.metadata["association_type_ids"] == ["228"]
    assert signal.metadata["association"]["association_types"][0]["label"] == "note_to_ticket"
    assert signal.metadata["raw"]["id"] == "note-1"
    assert "hubspot" in signal.tags
    assert "ticket" in signal.tags


@pytest.mark.asyncio
async def test_hubspot_ticket_notes_paginates_tickets_and_dedupes_notes() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/ticket-1/associations/notes") and request.url.params.get("after") is None:
            return httpx.Response(
                200,
                json={
                    "results": [{"toObjectId": "note-1"}],
                    "paging": {"next": {"after": "cursor-2"}},
                },
            )
        if request.url.path.endswith("/ticket-1/associations/notes"):
            return httpx.Response(200, json={"results": [{"toObjectId": "shared"}]})
        if request.url.path.endswith("/ticket-2/associations/notes"):
            return httpx.Response(200, json={"results": [{"toObjectId": "shared"}, {"toObjectId": "note-3"}]})
        note_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=_note(note_id, archived=note_id == "shared"))

    adapter = HubSpotTicketNotesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={"ticket_ids": ["ticket-1", "ticket-2"], "per_ticket_limit": 2, "association_page_limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    association_requests = [request for request in requests if "/associations/notes" in request.url.path]
    assert [request.url.params.get("after") for request in association_requests] == [None, "cursor-2", None]
    assert [signal.metadata["note_id"] for signal in signals] == ["note-1", "shared", "note-3"]
    assert [signal.metadata["ticket_id"] for signal in signals] == ["ticket-1", "ticket-1", "ticket-2"]
    assert signals[1].metadata["archived"] is True


@pytest.mark.asyncio
async def test_hubspot_ticket_notes_filters_created_after_and_association_type() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/associations/notes"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"toObjectId": "old", "associationTypes": [{"typeId": 228}]},
                        {"toObjectId": "new", "associationTypes": [{"typeId": 228}]},
                        {"toObjectId": "skipped", "associationTypes": [{"typeId": 999}]},
                    ]
                },
            )
        note_id = request.url.path.rsplit("/", 1)[-1]
        created_at = "2026-04-30T10:00:00Z" if note_id == "old" else "2026-05-03T10:00:00Z"
        return httpx.Response(200, json=_note(note_id, created_at=created_at, include_optional=False))

    adapter = HubSpotTicketNotesAdapter(
        token="hubspot-token",
        config={
            "ticket_id": "ticket-1",
            "association_type_ids": ["228"],
            "created_after": "2026-05-01T00:00:00Z",
            "properties": ["hs_note_body", "createdate"],
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    fetched_note_paths = [request.url.path for request in requests if "/crm/v3/objects/notes/" in request.url.path]
    assert fetched_note_paths == ["/crm/v3/objects/notes/old", "/crm/v3/objects/notes/new"]
    assert [signal.metadata["note_id"] for signal in signals] == ["new"]
    note_request = next(request for request in requests if request.url.path.endswith("/notes/old"))
    assert note_request.url.params.get_list("properties") == ["hs_note_body", "createdate"]


@pytest.mark.asyncio
async def test_hubspot_ticket_notes_uses_env_token_and_ticket_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/associations/notes"):
            return httpx.Response(200, json={"results": [{"toObjectId": "note-1"}]})
        return httpx.Response(200, json=_note("note-1"))

    adapter = HubSpotTicketNotesAdapter(
        config={"tickets": ["ticket-9"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert requests[0].url.path == "/crm/v4/objects/tickets/ticket-9/associations/notes"


@pytest.mark.asyncio
async def test_hubspot_ticket_notes_empty_without_required_config_or_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotTicketNotesAdapter(config={"ticket_ids": ["ticket-1"]}).fetch() == []
    assert await HubSpotTicketNotesAdapter(token="token").fetch() == []
    assert await HubSpotTicketNotesAdapter(token="token", config={"ticket_ids": ["ticket-1"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_hubspot_ticket_notes_http_or_non_json_failure_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = HubSpotTicketNotesAdapter(
        token="hubspot-token",
        config={"ticket_id": "ticket-1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=10) == []
