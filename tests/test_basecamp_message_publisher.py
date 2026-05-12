from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.basecamp_messages import BasecampMessagePublishError, BasecampMessagePublisher
from tests.test_stripe_customer_note_publisher import _unit


def test_builds_message_subject_and_body() -> None:
    unit = _unit()
    unit["evidence"] = {"links": ["https://evidence.example.test/1"]}
    publisher = BasecampMessagePublisher(account_id="acct", project_id="proj", message_board_id="board")

    payload = publisher.build_message_payload(unit).to_dict()

    assert payload["subject"] == "Max idea: Stripe Customer Note Publisher"
    assert "Billing teams need approved idea context." in payload["content"]
    assert "Write deterministic customer metadata." in payload["content"]
    assert "https://evidence.example.test/1" in payload["content"]
    assert payload["metadata"]["publisher"] == "max.basecamp_messages"


def test_from_env_reads_basecamp_message_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASECAMP_ACCOUNT_ID", "env-account")
    monkeypatch.setenv("BASECAMP_PROJECT_ID", "env-project")
    monkeypatch.setenv("BASECAMP_MESSAGE_BOARD_ID", "env-board")
    monkeypatch.setenv("BASECAMP_ACCESS_TOKEN", "env-token")
    monkeypatch.setenv("BASECAMP_API_URL", "https://basecamp.example.test")

    publisher = BasecampMessagePublisher.from_env(max_retries=3)

    assert publisher.account_id == "env-account"
    assert publisher.project_id == "env-project"
    assert publisher.message_board_id == "env-board"
    assert publisher.token == "env-token"
    assert publisher.api_url == "https://basecamp.example.test"
    assert publisher.max_retries == 3


def test_dry_run_avoids_network_and_returns_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = BasecampMessagePublisher(account_id="acct", project_id="proj", message_board_id="board", api_url="https://basecamp.example.test", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_unit(), dry_run=True)

    assert result.endpoint == "https://basecamp.example.test/acct/buckets/proj/message_boards/board/messages.json"
    assert result.payload["subject"] == "Max idea: Stripe Customer Note Publisher"


def test_live_publish_posts_bearer_request_and_parses_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 11, "app_url": "https://basecamp.example.test/messages/11"})

    publisher = BasecampMessagePublisher(account_id="acct", project_id="proj", message_board_id="board", token="bc-token", api_url="https://basecamp.example.test", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_unit(), dry_run=False)

    assert result.message_id == "11"
    assert result.message_url == "https://basecamp.example.test/messages/11"
    assert requests[0].headers["Authorization"] == "Bearer bc-token"
    posted = json.loads(requests[0].read())
    assert posted["subject"] == "Max idea: Stripe Customer Note Publisher"


def test_missing_auth_and_retry_redaction() -> None:
    publisher = BasecampMessagePublisher(account_id="acct", project_id="proj", message_board_id="board")

    with pytest.raises(BasecampMessagePublishError, match="BASECAMP_ACCESS_TOKEN"):
        publisher.publish(_unit(), dry_run=False)

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="bad Bearer bc-token")

    retrying = BasecampMessagePublisher(account_id="acct", project_id="proj", message_board_id="board", token="bc-token", max_retries=1, client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(BasecampMessagePublishError) as exc:
        retrying.publish(_unit(), dry_run=False)

    assert calls == 2
    assert "bc-token" not in str(exc.value)
