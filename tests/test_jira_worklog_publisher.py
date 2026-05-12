"""Tests for Jira worklog publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher.jira_worklogs import JiraWorklogPublishError, JiraWorklogPublisher


def _idea_payload() -> dict:
    return {
        "source": {"system": "max", "type": "idea", "idea_id": "bu-jira001"},
        "project": {"title": "Jira Worklog Publisher", "summary": "Attach Max planning time to Jira."},
        "execution": {"validation_plan": "Log one validation session."},
        "evaluation": {"overall_score": 81.0, "recommendation": "ship"},
    }


def _design_brief_payload() -> dict:
    return {
        "design_brief": {
            "id": "dbf-jira001",
            "title": "Jira Worklog Design Brief",
            "summary": "Track planning work against Jira issues.",
            "readiness_score": 84.0,
            "recommendation": "ready",
            "source_idea_ids": ["bu-jira001"],
        }
    }


def test_dry_run_validates_issue_and_returns_endpoint_payload_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = JiraWorklogPublisher(
        "https://acme.atlassian.net",
        issue_key="MAX-123",
        account_id="acc-1",
        started="2026-05-12T10:00:00.000+0000",
        time_spent_seconds=3600,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.dry_run is True
    assert result.endpoint == "https://acme.atlassian.net/rest/api/3/issue/MAX-123/worklog"
    assert result.payload["timeSpentSeconds"] == 3600
    assert result.payload["started"] == "2026-05-12T10:00:00.000+0000"
    assert "Jira Worklog Publisher" in result.payload["comment"]
    assert result.payload["metadata"]["account_id"] == "acc-1"


def test_design_brief_renders_worklog_comment() -> None:
    publisher = JiraWorklogPublisher("https://acme.atlassian.net", issue_key="MAX-123")

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    assert "Jira Worklog Design Brief" in result.payload["comment"]
    assert "Readiness: 84.0" in result.payload["comment"]
    assert "Source ideas: bu-jira001" in result.payload["comment"]
    assert result.payload["metadata"]["design_brief_id"] == "dbf-jira001"


def test_live_publish_posts_worklog_and_returns_id_and_self_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "10001", "self": "https://acme.atlassian.net/rest/api/3/issue/MAX-123/worklog/10001"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraWorklogPublisher(
        "https://acme.atlassian.net",
        issue_key="MAX-123",
        auth_email="ada@example.com",
        api_token="jira-token",
        started="2026-05-12T10:00:00.000+0000",
        client=client,
    )

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.status_code == 201
    assert result.worklog_id == "10001"
    assert result.worklog_url.endswith("/10001")
    assert requests[0].headers["Authorization"] == "Basic " + base64.b64encode(b"ada@example.com:jira-token").decode("ascii")
    posted = json.loads(requests[0].read())
    assert posted["timeSpentSeconds"] == 1800
    assert posted["comment"]["type"] == "doc"


def test_live_publish_uses_bearer_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "10002"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraWorklogPublisher("https://acme.atlassian.net", issue_key="MAX-123", bearer_token="bearer-token", client=client)

    publisher.publish(_idea_payload(), dry_run=False)

    assert requests[0].headers["Authorization"] == "Bearer bearer-token"


def test_missing_issue_key_raises_publish_error() -> None:
    publisher = JiraWorklogPublisher("https://acme.atlassian.net")

    with pytest.raises(JiraWorklogPublishError, match="issue_key"):
        publisher.publish(_idea_payload(), dry_run=True)


def test_live_publish_requires_auth() -> None:
    publisher = JiraWorklogPublisher("https://acme.atlassian.net", issue_key="MAX-123")

    with pytest.raises(JiraWorklogPublishError, match="auth_email"):
        publisher.publish(_idea_payload(), dry_run=False)


def test_provider_error_redacts_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="bad token=jira-token Authorization=Bearer jira-token")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraWorklogPublisher("https://acme.atlassian.net", issue_key="MAX-123", bearer_token="jira-token", client=client)

    with pytest.raises(JiraWorklogPublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert exc.value.status_code == 403
    assert "jira-token" not in str(exc.value)
