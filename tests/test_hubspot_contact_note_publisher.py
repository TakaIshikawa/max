from __future__ import annotations

import json

import httpx

from max.publisher.hubspot_contact_notes import HubSpotContactNotePublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_returns_note_body_and_contact_association_payload() -> None:
    publisher = HubSpotContactNotePublisher(contact_id="123", api_url="https://hubspot.example.test")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.endpoint == "https://hubspot.example.test/crm/v3/objects/notes"
    assert result.payload["contact_id"] == "123"
    assert "Zoom Chat Publisher" in result.payload["properties"]["hs_note_body"]
    assert result.payload["associations"][0]["to"]["id"] == "123"


def test_from_env_reads_hubspot_contact_note_configuration(monkeypatch) -> None:
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hub-token")
    monkeypatch.setenv("HUBSPOT_CONTACT_ID", "contact-env")
    monkeypatch.setenv("HUBSPOT_API_URL", "https://hubspot.example.test")

    publisher = HubSpotContactNotePublisher.from_env()

    assert publisher.access_token == "hub-token"
    assert publisher.contact_id == "contact-env"
    assert publisher.api_url == "https://hubspot.example.test"


def test_live_publish_posts_bearer_json_and_returns_note_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "note-1"})

    publisher = HubSpotContactNotePublisher(contact_id="123", access_token="hub-token", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.note_id == "note-1"
    assert requests[0].headers["Authorization"] == "Bearer hub-token"
    assert json.loads(requests[0].read())["associations"][0]["to"]["id"] == "123"
