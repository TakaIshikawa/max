from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher.freshservice_ticket_notes import FreshserviceTicketNotePublishError, FreshserviceTicketNotePublisher
from tests.test_stripe_customer_note_publisher import _unit


def test_builds_freshservice_note_body_and_endpoint() -> None:
    publisher = FreshserviceTicketNotePublisher(ticket_id="42", domain="acme")

    result = publisher.publish(_unit(), dry_run=True)

    assert result.endpoint == "https://acme.freshservice.com/api/v2/tickets/42/notes"
    assert result.payload["private"] is True
    assert "Problem: Billing teams need approved idea context." in result.payload["body"]
    assert "Solution: Write deterministic customer metadata." in result.payload["body"]
    assert result.payload["metadata"]["publisher"] == "max.freshservice_ticket_notes"


def test_from_env_reads_freshservice_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRESHSERVICE_TICKET_ID", "99")
    monkeypatch.setenv("FRESHSERVICE_API_KEY", "fresh-key")
    monkeypatch.setenv("FRESHSERVICE_API_URL", "https://fresh.example.test")

    publisher = FreshserviceTicketNotePublisher.from_env(timeout=2.5, max_retries=3)

    assert publisher.ticket_id == "99"
    assert publisher.api_key == "fresh-key"
    assert publisher.api_url == "https://fresh.example.test"
    assert publisher.timeout == 2.5
    assert publisher.max_retries == 3


def test_live_publish_posts_note_and_returns_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"note": {"id": 123}})

    publisher = FreshserviceTicketNotePublisher(
        ticket_id="42",
        api_key="fresh-key",
        api_url="https://fresh.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=False, private=False)

    assert result.note_id == "123"
    expected_auth = base64.b64encode(b"fresh-key:X").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert json.loads(requests[0].read())["private"] is False


def test_freshservice_retry_failure_exposes_status_code() -> None:
    publisher = FreshserviceTicketNotePublisher(
        ticket_id="42",
        api_key="fresh-key",
        max_retries=1,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable fresh-key"))),
    )

    with pytest.raises(FreshserviceTicketNotePublishError) as exc:
        publisher.publish(_unit(), dry_run=False)

    assert exc.value.status_code == 503
    assert "fresh-key" not in str(exc.value)
