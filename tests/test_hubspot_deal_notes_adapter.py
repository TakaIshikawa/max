"""Tests for HubSpot deal notes import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_deal_notes_adapter import HubSpotDealNoteAdapter, HubSpotDealNotesAdapter


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
            "hs_note_body": body or f"Deal note {note_id}",
            "hs_timestamp": created_at,
            "createdate": created_at,
        },
    }
    if include_optional:
        note["properties"]["hubspot_owner_id"] = "owner-1"
        note["properties"]["hs_lastmodifieddate"] = "2026-05-02T10:00:00Z"
    return note


@pytest.mark.asyncio
async def test_hubspot_deal_notes_fetches_associated_notes_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/crm/v4/objects/deals/deal-1/associations/notes":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "toObjectId": "note-1",
                            "associationTypes": [
                                {"typeId": 214, "category": "HUBSPOT_DEFINED", "label": "note_to_deal"}
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(200, json=_note("note-1", body="Procurement asked about renewal."))

    adapter = HubSpotDealNotesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={"deal_ids": ["deal-1"], "association_type_id": 214},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert HubSpotDealNoteAdapter is HubSpotDealNotesAdapter
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
    assert signal.id == "hubspot-deal-note:deal-1:note-1"
    assert signal.source_adapter == "hubspot_deal_notes_import"
    assert signal.source_type.value == "market"
    assert signal.title == "HubSpot deal deal-1 note"
    assert signal.content == "Procurement asked about renewal."
    assert signal.author == "owner-1"
    assert signal.metadata["signal_role"] == "sales"
    assert signal.metadata["deal_id"] == "deal-1"
    assert signal.metadata["note_id"] == "note-1"
    assert signal.metadata["body"] == "Procurement asked about renewal."
    assert signal.metadata["association_type_ids"] == ["214"]
    assert signal.metadata["association"]["association_types"][0]["label"] == "note_to_deal"
    assert "hubspot" in signal.tags
    assert "deal" in signal.tags


@pytest.mark.asyncio
async def test_hubspot_deal_notes_paginates_deals_and_preserves_archived_notes() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/deal-1/associations/notes") and request.url.params.get("after") is None:
            return httpx.Response(
                200,
                json={
                    "results": [{"toObjectId": "note-1"}],
                    "paging": {"next": {"after": "cursor-2"}},
                },
            )
        if request.url.path.endswith("/deal-1/associations/notes"):
            return httpx.Response(200, json={"results": [{"toObjectId": "note-2"}]})
        if request.url.path.endswith("/deal-2/associations/notes"):
            return httpx.Response(200, json={"results": [{"toObjectId": "note-3"}]})
        note_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=_note(note_id, archived=note_id == "note-2"))

    adapter = HubSpotDealNotesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={"deal_ids": ["deal-1", "deal-2"], "per_deal_limit": 2, "association_page_limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    association_requests = [request for request in requests if "/associations/notes" in request.url.path]
    assert [request.url.params.get("after") for request in association_requests] == [None, "cursor-2", None]
    assert [signal.metadata["note_id"] for signal in signals] == ["note-1", "note-2", "note-3"]
    assert [signal.metadata["deal_id"] for signal in signals] == ["deal-1", "deal-1", "deal-2"]
    assert signals[1].metadata["archived"] is True


@pytest.mark.asyncio
async def test_hubspot_deal_notes_handles_missing_optional_properties_and_association_type_filter() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/associations/notes"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"toObjectId": "note-1", "associationTypes": [{"typeId": 214}]},
                        {"toObjectId": "note-skipped", "associationTypes": [{"typeId": 999}]},
                    ]
                },
            )
        return httpx.Response(200, json=_note("note-1", include_optional=False))

    adapter = HubSpotDealNotesAdapter(
        token="hubspot-token",
        config={"deal_id": "deal-1", "association_type_ids": ["214"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    fetched_note_paths = [request.url.path for request in requests if "/crm/v3/objects/notes/" in request.url.path]
    assert fetched_note_paths == ["/crm/v3/objects/notes/note-1"]
    assert len(signals) == 1
    assert signals[0].author is None
    assert signals[0].metadata["owner_id"] is None
    assert signals[0].metadata["updated_at"] == "2026-05-02T10:00:00Z"


@pytest.mark.asyncio
async def test_hubspot_deal_notes_empty_without_required_config_or_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotDealNotesAdapter(config={"deal_ids": ["deal-1"]}).fetch() == []
    assert await HubSpotDealNotesAdapter(token="token").fetch() == []
    assert await HubSpotDealNotesAdapter(token="token", config={"deal_ids": ["deal-1"]}).fetch(limit=0) == []
