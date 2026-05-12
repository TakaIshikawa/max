from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.calendly_invitee_notes import CalendlyInviteeNotePublishError, CalendlyInviteeNotePublisher
from tests.test_stripe_customer_note_publisher import _unit


def _unit_with_links() -> dict:
    unit = _unit()
    unit["execution"] = {"validation_plan": "Review with a scheduled buyer."}
    unit["evidence"] = {"links": ["https://example.test/evidence"]}
    return unit


def test_accepts_uuid_and_returns_normalized_dry_run_payload() -> None:
    publisher = CalendlyInviteeNotePublisher(invitee_uuid="inv_123", api_url="https://calendly.example.test")

    result = publisher.publish(_unit_with_links(), dry_run=True)

    assert result.endpoint == "https://calendly.example.test/invitees/inv_123/notes"
    assert result.payload["invitee_uri"] == "https://calendly.example.test/invitees/inv_123"
    assert "Stripe Customer Note Publisher" in result.payload["note"]
    assert "Validation plan: Review with a scheduled buyer." in result.payload["note"]
    assert "Evidence links: https://example.test/evidence" in result.payload["note"]
    assert result.payload["metadata"]["idea_id"] == "bu-stripe001"


def test_accepts_full_invitee_uri_and_normalizes_to_configured_api_url() -> None:
    publisher = CalendlyInviteeNotePublisher(
        invitee_uri="https://api.calendly.com/scheduled_events/event-1/invitees/inv_123",
        api_url="https://calendly.example.test",
    )

    assert publisher.invitee_notes_endpoint() == "https://calendly.example.test/scheduled_events/event-1/invitees/inv_123/notes"


def test_from_env_reads_calendly_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALENDLY_INVITEE_UUID", "env-invitee")
    monkeypatch.setenv("CALENDLY_API_TOKEN", "env-token")
    monkeypatch.setenv("CALENDLY_API_URL", "https://calendly.example.test")

    publisher = CalendlyInviteeNotePublisher.from_env(max_retries=5)

    assert publisher.invitee_uuid == "env-invitee"
    assert publisher.token == "env-token"
    assert publisher.api_url == "https://calendly.example.test"
    assert publisher.max_retries == 5


def test_live_publish_posts_note_and_returns_uri() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"resource": {"uri": "https://api.calendly.com/notes/note-1"}})

    publisher = CalendlyInviteeNotePublisher(
        invitee_uuid="inv_123",
        token="cal-token",
        api_url="https://calendly.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit_with_links(), dry_run=False)

    assert result.note_uri == "https://api.calendly.com/notes/note-1"
    assert requests[0].headers["Authorization"] == "Bearer cal-token"
    assert json.loads(requests[0].read())["note"].startswith("Stripe Customer Note Publisher")


def test_calendly_retry_failure_exposes_status_code() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500, text="error")))
    publisher = CalendlyInviteeNotePublisher(invitee_uuid="inv_123", token="cal-token", max_retries=1, client=client)

    with pytest.raises(CalendlyInviteeNotePublishError) as exc:
        publisher.publish(_unit(), dry_run=False)

    assert exc.value.status_code == 500
