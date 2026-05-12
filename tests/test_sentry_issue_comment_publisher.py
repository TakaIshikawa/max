from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.sentry_issue_comments import SentryIssueCommentPublishError, SentryIssueCommentPublisher
from tests.test_stripe_customer_note_publisher import _unit


def test_builds_sentry_endpoint_and_markdown_body() -> None:
    publisher = SentryIssueCommentPublisher(organization_slug="acme", issue_id="123")

    result = publisher.publish(_unit(), dry_run=True)

    assert result.endpoint == "https://sentry.io/api/0/organizations/acme/issues/123/comments/"
    assert "## Max idea: Stripe Customer Note Publisher" in result.payload["text"]
    assert "- Problem: Billing teams need approved idea context." in result.payload["text"]
    assert "- Solution: Write deterministic customer metadata." in result.payload["text"]
    assert result.payload["metadata"]["publisher"] == "max.sentry_issue_comments"


def test_from_env_reads_sentry_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "sentry-token")
    monkeypatch.setenv("SENTRY_ORG", "env-org")
    monkeypatch.setenv("SENTRY_ISSUE_ID", "env-issue")
    monkeypatch.setenv("SENTRY_API_URL", "https://sentry.example.test/api/0")

    publisher = SentryIssueCommentPublisher.from_env(timeout=2.5, max_retries=3)

    assert publisher.token == "sentry-token"
    assert publisher.organization_slug == "env-org"
    assert publisher.issue_id == "env-issue"
    assert publisher.api_url == "https://sentry.example.test/api/0"
    assert publisher.timeout == 2.5
    assert publisher.max_retries == 3


def test_live_publish_posts_comment_and_returns_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "comment-1"})

    publisher = SentryIssueCommentPublisher(
        organization_slug="acme",
        issue_id="123",
        token="sentry-token",
        api_url="https://sentry.example.test/api/0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_unit(), dry_run=False)

    assert result.comment_id == "comment-1"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert "Stripe Customer Note Publisher" in json.loads(requests[0].read())["text"]


def test_sentry_retry_failure_exposes_status_code() -> None:
    publisher = SentryIssueCommentPublisher(
        organization_slug="acme",
        issue_id="123",
        token="sentry-token",
        max_retries=1,
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable sentry-token"))),
    )

    with pytest.raises(SentryIssueCommentPublishError) as exc:
        publisher.publish(_unit(), dry_run=False)

    assert exc.value.status_code == 503
    assert "sentry-token" not in str(exc.value)
