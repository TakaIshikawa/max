from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher.customerio_events import CustomerIOEventPublishError, CustomerIOEventPublisher
from tests.test_stripe_customer_note_publisher import _unit


def test_builds_customerio_event_payload_with_max_idea_data() -> None:
    unit = _unit() | {"created_at": "2026-05-12T00:00:00Z"}
    publisher = CustomerIOEventPublisher(customer_id="cio-customer-1", event_name="max.idea.approved")

    payload = publisher.build_event_payload(unit).to_dict()

    assert payload == {
        "customer_id": "cio-customer-1",
        "name": "max.idea.approved",
        "timestamp": 1778544000,
        "data": {
            "max_category": "billing",
            "max_idea_id": "bu-stripe001",
            "max_problem": "Billing teams need approved idea context.",
            "max_score": "87.0",
            "max_solution": "Write deterministic customer metadata.",
            "max_status": "approved",
            "max_title": "Stripe Customer Note Publisher",
            "publisher": "max.customerio_events",
        },
    }


def test_from_env_reads_customerio_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMERIO_SITE_ID", "site-env")
    monkeypatch.setenv("CUSTOMERIO_API_KEY", "key-env")
    monkeypatch.setenv("CUSTOMERIO_CUSTOMER_ID", "customer-env")
    monkeypatch.setenv("CUSTOMERIO_EVENT_NAME", "max.idea.env")
    monkeypatch.setenv("CUSTOMERIO_API_URL", "https://customerio.example.test")

    publisher = CustomerIOEventPublisher.from_env(timeout=2.5, max_retries=3)

    assert publisher.site_id == "site-env"
    assert publisher.api_key == "key-env"
    assert publisher.customer_id == "customer-env"
    assert publisher.event_name == "max.idea.env"
    assert publisher.api_url == "https://customerio.example.test"
    assert publisher.timeout == 2.5
    assert publisher.max_retries == 3


def test_dry_run_returns_redacted_request_details_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = CustomerIOEventPublisher(
        site_id="site-id",
        api_key="secret-key",
        customer_id="customer-1",
        event_name="max.idea.approved",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=True, timestamp=123)

    assert result.dry_run is True
    assert result.endpoint == "https://track.customer.io/api/v1/customers/customer-1/events"
    assert result.payload["timestamp"] == 123
    assert result.request == {
        "method": "POST",
        "headers": {
            "Accept": "application/json",
            "Authorization": "Basic [REDACTED]",
            "Content-Type": "application/json",
            "User-Agent": "max-customerio-events-publisher/1",
        },
    }
    assert "secret-key" not in str(result.request)


def test_live_publish_uses_basic_auth_and_parses_response_identifiers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"event_id": "evt_123", "queued": True})

    publisher = CustomerIOEventPublisher(
        site_id="site-id",
        api_key="secret-key",
        customer_id="customer-1",
        event_name="max.idea.approved",
        api_url="https://customerio.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=False, timestamp=456)

    assert result.status_code == 200
    assert result.event_id == "evt_123"
    assert result.response == {"event_id": "evt_123", "queued": True}
    assert requests[0].url == "https://customerio.example.test/api/v1/customers/customer-1/events"
    expected_auth = base64.b64encode(b"site-id:secret-key").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    posted = json.loads(requests[0].read())
    assert posted["name"] == "max.idea.approved"
    assert posted["timestamp"] == 456
    assert posted["data"]["max_idea_id"] == "bu-stripe001"


def test_live_publish_requires_customerio_credentials() -> None:
    publisher = CustomerIOEventPublisher(customer_id="customer-1")

    with pytest.raises(CustomerIOEventPublishError, match="CUSTOMERIO_SITE_ID"):
        publisher.publish(_unit(), dry_run=False)


def test_retryable_errors_are_retried_before_success() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, text="temporarily unavailable")
        return httpx.Response(200, json={"id": "evt_retry"})

    publisher = CustomerIOEventPublisher(
        site_id="site-id",
        api_key="secret-key",
        customer_id="customer-1",
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=False)

    assert calls == 2
    assert result.event_id == "evt_retry"


def test_permanent_failure_raises_custom_error_with_redacted_secret() -> None:
    publisher = CustomerIOEventPublisher(
        site_id="site-id",
        api_key="secret-key",
        customer_id="customer-1",
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(400, text="bad secret-key"))),
    )

    with pytest.raises(CustomerIOEventPublishError, match="HTTP 400") as exc:
        publisher.publish(_unit(), dry_run=False)

    assert exc.value.status_code == 400
    assert "secret-key" not in str(exc.value)
