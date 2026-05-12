from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.sentry_issue_assignment import (
    SentryIssueAssignmentPublishError,
    SentryIssueAssignmentPublisher,
)


def test_dry_run_builds_assignment_payload_without_network_call() -> None:
    publisher = SentryIssueAssignmentPublisher(
        issue_id="123",
        assignee="user:42",
        status="inProgress",
        client=httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("dry run should not make network calls")))),
    )

    result = publisher.publish(dry_run=True)

    assert result.status_code is None
    assert result.dry_run is True
    assert result.issue_id == "123"
    assert result.assigned_to == "user:42"
    assert result.endpoint == "https://sentry.io/api/0/issues/123/"
    assert result.payload == {
        "issue_id": "123",
        "assignedTo": "user:42",
        "status": "inProgress",
    }


def test_from_env_reads_sentry_assignment_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "sentry-token")
    monkeypatch.setenv("SENTRY_ISSUE_ID", "env-issue")
    monkeypatch.setenv("SENTRY_ASSIGNEE", "team:platform")
    monkeypatch.setenv("SENTRY_ISSUE_STATUS", "resolved")
    monkeypatch.setenv("SENTRY_API_URL", "https://sentry.example.test/api/0")

    publisher = SentryIssueAssignmentPublisher.from_env(timeout=2.5)

    assert publisher.token == "sentry-token"
    assert publisher.issue_id == "env-issue"
    assert publisher.assignee == "team:platform"
    assert publisher.status == "resolved"
    assert publisher.api_url == "https://sentry.example.test/api/0"
    assert publisher.timeout == 2.5


def test_live_publish_puts_assignment_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "123", "assignedTo": "user:42"})

    publisher = SentryIssueAssignmentPublisher(
        issue_id="123",
        assignee="user:42",
        token="sentry-token",
        api_url="https://sentry.example.test/api/0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(dry_run=False, status="resolved")

    assert result.status_code == 200
    assert result.response == {"id": "123", "assignedTo": "user:42"}
    assert requests[0].method == "PUT"
    assert requests[0].url == "https://sentry.example.test/api/0/issues/123/"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert requests[0].headers["User-Agent"] == "max-sentry-issue-assignment-publisher/1"
    assert json.loads(requests[0].read()) == {"assignedTo": "user:42", "status": "resolved"}


def test_requires_issue_and_assignee() -> None:
    publisher = SentryIssueAssignmentPublisher()

    with pytest.raises(ValueError, match="issue_id is required"):
        publisher.publish(dry_run=True)

    publisher = SentryIssueAssignmentPublisher(issue_id="123")
    with pytest.raises(ValueError, match="assignee is required"):
        publisher.publish(dry_run=True)


def test_live_publish_requires_token() -> None:
    publisher = SentryIssueAssignmentPublisher(issue_id="123", assignee="user:42")

    with pytest.raises(SentryIssueAssignmentPublishError, match="SENTRY_AUTH_TOKEN"):
        publisher.publish(dry_run=False)


def test_error_redacts_token_and_includes_status() -> None:
    publisher = SentryIssueAssignmentPublisher(
        issue_id="123",
        assignee="user:42",
        token="sentry-token",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(503, text="bad sentry-token"))
        ),
    )

    with pytest.raises(SentryIssueAssignmentPublishError, match="HTTP 503") as exc:
        publisher.publish(dry_run=False)

    assert exc.value.status_code == 503
    assert "sentry-token" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)
