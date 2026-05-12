from __future__ import annotations

import json

import httpx

from max.publisher.hubspot_tickets import HubSpotTicketPublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_builds_hubspot_ticket_payload() -> None:
    publisher = HubSpotTicketPublisher(
        pipeline="support",
        pipeline_stage="new",
        owner_id="owner-1",
        priority="HIGH",
        category="PRODUCT",
        subject="Custom subject",
        api_url="https://hubspot.example",
    )

    result = publisher.publish(_idea_payload(), dry_run=True)

    props = result.payload["properties"]
    assert result.endpoint == "https://hubspot.example/crm/v3/objects/tickets"
    assert props["subject"] == "Custom subject"
    assert "Zoom Chat Publisher" in props["content"]
    assert props["hs_pipeline"] == "support"
    assert props["hs_pipeline_stage"] == "new"
    assert props["hubspot_owner_id"] == "owner-1"
    assert props["hs_ticket_priority"] == "HIGH"
    assert props["hs_ticket_category"] == "PRODUCT"
    assert props["max_idea_id"] == "bu-zoom001"


def test_from_env_reads_hubspot_ticket_configuration(monkeypatch) -> None:
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hub-token")
    monkeypatch.setenv("HUBSPOT_TICKET_PIPELINE", "pipe")
    monkeypatch.setenv("HUBSPOT_TICKET_PIPELINE_STAGE", "stage")
    monkeypatch.setenv("HUBSPOT_OWNER_ID", "owner")
    monkeypatch.setenv("HUBSPOT_TICKET_PRIORITY", "LOW")
    monkeypatch.setenv("HUBSPOT_TICKET_CATEGORY", "GENERAL")
    monkeypatch.setenv("HUBSPOT_API_URL", "https://hubspot.example")

    publisher = HubSpotTicketPublisher.from_env()

    assert publisher.access_token == "hub-token"
    assert publisher.pipeline == "pipe"
    assert publisher.pipeline_stage == "stage"
    assert publisher.owner_id == "owner"
    assert publisher.priority == "LOW"
    assert publisher.category == "GENERAL"
    assert publisher.api_url == "https://hubspot.example"


def test_live_publish_posts_bearer_json_and_returns_ticket_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "ticket-1", "archived": False})

    publisher = HubSpotTicketPublisher(access_token="hub-token", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.ticket_id == "ticket-1"
    assert result.archived is False
    assert requests[0].headers["Authorization"] == "Bearer hub-token"
    assert json.loads(requests[0].read())["properties"]["subject"] == "Zoom Chat Publisher"
