from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.basecamp_todos import BasecampTodoPublishError, BasecampTodoPublisher
from tests.test_stripe_customer_note_publisher import _unit


def test_dry_run_constructs_endpoint_and_payload_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = BasecampTodoPublisher(
        account_id="acct-1",
        project_id="proj-1",
        todolist_id="list-1",
        api_url="https://basecamp.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=True)

    assert result.endpoint == "https://basecamp.example.test/acct-1/buckets/proj-1/todolists/list-1/todos.json"
    assert result.payload["title"] == "Validate Max idea: Stripe Customer Note Publisher"
    assert "Problem: Billing teams need approved idea context." in result.payload["description"]
    assert "Solution: Write deterministic customer metadata." in result.payload["description"]
    assert result.payload["metadata"]["publisher"] == "max.basecamp_todos"


def test_from_env_reads_basecamp_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASECAMP_ACCOUNT_ID", "env-account")
    monkeypatch.setenv("BASECAMP_PROJECT_ID", "env-project")
    monkeypatch.setenv("BASECAMP_TODOLIST_ID", "env-list")
    monkeypatch.setenv("BASECAMP_ACCESS_TOKEN", "env-token")
    monkeypatch.setenv("BASECAMP_API_URL", "https://basecamp.example.test")

    publisher = BasecampTodoPublisher.from_env(timeout=2.5, max_retries=3)

    assert publisher.account_id == "env-account"
    assert publisher.project_id == "env-project"
    assert publisher.todolist_id == "env-list"
    assert publisher.token == "env-token"
    assert publisher.api_url == "https://basecamp.example.test"
    assert publisher.timeout == 2.5
    assert publisher.max_retries == 3


def test_live_publish_posts_todo_and_returns_id_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 99, "app_url": "https://basecamp.example.test/todos/99"})

    publisher = BasecampTodoPublisher(
        account_id="acct-1",
        project_id="proj-1",
        todolist_id="list-1",
        token="bc-token",
        api_url="https://basecamp.example.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=False)

    assert result.todo_id == "99"
    assert result.todo_url == "https://basecamp.example.test/todos/99"
    assert requests[0].headers["Authorization"] == "Bearer bc-token"
    posted = json.loads(requests[0].read())
    assert posted["content"] == "Validate Max idea: Stripe Customer Note Publisher"


def test_basecamp_retry_failure_exposes_status_code() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable")))
    publisher = BasecampTodoPublisher(
        account_id="acct-1",
        project_id="proj-1",
        todolist_id="list-1",
        token="bc-token",
        max_retries=1,
        client=client,
    )

    with pytest.raises(BasecampTodoPublishError) as exc:
        publisher.publish(_unit(), dry_run=False)

    assert exc.value.status_code == 503
