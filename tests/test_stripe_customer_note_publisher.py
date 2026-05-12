from __future__ import annotations

import httpx
import pytest

from max.publisher.stripe_customer_notes import StripeCustomerNotePublishError, StripeCustomerNotePublisher


def _unit() -> dict:
    return {
        "source": {"idea_id": "bu-stripe001", "status": "approved", "category": "billing"},
        "project": {"title": "Stripe Customer Note Publisher", "summary": "Attach Max context to Stripe customers."},
        "problem": {"statement": "Billing teams need approved idea context."},
        "solution": {"approach": "Write deterministic customer metadata."},
        "evaluation": {"overall_score": 87.0},
    }


def test_builds_deterministic_stripe_metadata_payload() -> None:
    publisher = StripeCustomerNotePublisher(customer_id="cus_123")

    payload = publisher.build_customer_note_payload(_unit()).to_dict()

    assert payload == {
        "customer_id": "cus_123",
        "metadata": {
            "max_category": "billing",
            "max_idea_id": "bu-stripe001",
            "max_problem": "Billing teams need approved idea context.",
            "max_score": "87.0",
            "max_solution": "Write deterministic customer metadata.",
            "max_status": "approved",
            "max_title": "Stripe Customer Note Publisher",
        },
    }


def test_from_env_reads_stripe_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_CUSTOMER_ID", "cus_env")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_env")
    monkeypatch.setenv("STRIPE_API_URL", "https://stripe.example.test")

    publisher = StripeCustomerNotePublisher.from_env()

    assert publisher.customer_id == "cus_env"
    assert publisher.api_key == "sk_env"
    assert publisher.api_url == "https://stripe.example.test"


def test_dry_run_returns_payload_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = StripeCustomerNotePublisher(
        customer_id="cus_123",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=True)

    assert result.dry_run is True
    assert result.endpoint == "https://api.stripe.com/v1/customers/cus_123"
    assert result.payload["metadata"]["max_idea_id"] == "bu-stripe001"


def test_live_publish_posts_form_encoded_metadata_and_parses_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "cus_123", "object": "customer"})

    publisher = StripeCustomerNotePublisher(
        customer_id="cus_123",
        api_key="sk_test",
        api_url="https://stripe.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=False)

    assert result.status_code == 200
    assert result.response == {"id": "cus_123", "object": "customer"}
    assert requests[0].url == "https://stripe.example.test/v1/customers/cus_123"
    assert requests[0].headers["Authorization"] == "Bearer sk_test"
    posted = requests[0].read().decode()
    assert "metadata%5Bmax_title%5D=Stripe+Customer+Note+Publisher" in posted
    assert "metadata%5Bmax_idea_id%5D=bu-stripe001" in posted


def test_live_publish_requires_api_key() -> None:
    publisher = StripeCustomerNotePublisher(customer_id="cus_123")

    with pytest.raises(StripeCustomerNotePublishError, match="STRIPE_API_KEY"):
        publisher.publish(_unit(), dry_run=False)


def test_missing_customer_id_is_actionable() -> None:
    publisher = StripeCustomerNotePublisher(api_key="sk_test")

    with pytest.raises(StripeCustomerNotePublishError, match="STRIPE_CUSTOMER_ID"):
        publisher.publish(_unit(), dry_run=True)


def test_retryable_failure_retries_and_exposes_status_code() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="temporarily unavailable sk_test")

    publisher = StripeCustomerNotePublisher(
        customer_id="cus_123",
        api_key="sk_test",
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(StripeCustomerNotePublishError, match="HTTP 503") as exc:
        publisher.publish(_unit(), dry_run=False)

    assert calls == 3
    assert exc.value.status_code == 503
    assert "sk_test" not in str(exc.value)
