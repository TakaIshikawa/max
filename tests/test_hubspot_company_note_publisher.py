from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.hubspot_company_notes import HubSpotCompanyNotePublishError, HubSpotCompanyNotePublisher
from tests.test_stripe_customer_note_publisher import _unit


def test_dry_run_returns_hubspot_payload_and_endpoint_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = HubSpotCompanyNotePublisher(
        company_id="12345",
        api_url="https://hubspot.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=True)

    assert result.endpoint == "https://hubspot.example.test/crm/v3/objects/notes"
    assert result.payload["company_id"] == "12345"
    assert "Stripe Customer Note Publisher" in result.payload["properties"]["hs_note_body"]
    assert "Idea ID: bu-stripe001" in result.payload["properties"]["hs_note_body"]
    assert result.payload["metadata"]["publisher"] == "max.hubspot_company_notes"
    assert result.payload["associations"][0]["to"]["id"] == "12345"


def test_from_env_reads_hubspot_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUBSPOT_COMPANY_ID", "env-company")
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "env-token")
    monkeypatch.setenv("HUBSPOT_API_URL", "https://hubspot.example.test")

    publisher = HubSpotCompanyNotePublisher.from_env(timeout=3.0, max_retries=4)

    assert publisher.company_id == "env-company"
    assert publisher.token == "env-token"
    assert publisher.api_url == "https://hubspot.example.test"
    assert publisher.timeout == 3.0
    assert publisher.max_retries == 4


def test_live_publish_posts_hubspot_note_and_returns_note_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "note-1"})

    publisher = HubSpotCompanyNotePublisher(
        company_id="12345",
        token="hub-token",
        api_url="https://hubspot.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=False)

    assert result.note_id == "note-1"
    assert requests[0].headers["Authorization"] == "Bearer hub-token"
    posted = json.loads(requests[0].read())
    assert posted["associations"][0]["to"]["id"] == "12345"


def test_hubspot_retry_failure_exposes_status_code() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429, text="slow down")))
    publisher = HubSpotCompanyNotePublisher(company_id="12345", token="hub-token", max_retries=1, client=client)

    with pytest.raises(HubSpotCompanyNotePublishError) as exc:
        publisher.publish(_unit(), dry_run=False)

    assert exc.value.status_code == 429
