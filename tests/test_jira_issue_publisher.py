"""Tests for Jira issue publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher.jira_issues import JiraIssuePublishError, JiraIssuePublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-jira001",
            "status": "approved",
            "domain": "devtools",
            "category": "automation",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Jira Publish Idea",
            "summary": "Publish implementation-ready ideas to Jira",
            "target_users": "developers",
        },
        "problem": {"statement": "Reviewed ideas are trapped in Max"},
        "solution": {"approach": "Create Jira issues through REST"},
        "execution": {
            "mvp_scope": ["Jira publisher", "REST endpoint"],
            "validation_plan": "Publish one approved idea into a test project.",
        },
        "evidence": {
            "rationale": "Teams triage in Jira.",
            "insight_ids": ["ins-jira001"],
            "signal_ids": ["sig-jira001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": [],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
        },
    }


def test_build_issue_payload_maps_tact_spec_fields() -> None:
    publisher = JiraIssuePublisher(
        "https://example.atlassian.net",
        "MAX",
        issue_type="Story",
        labels=["delivery"],
    )

    payload = publisher.build_issue_payload(_tact_spec()).to_dict()

    assert payload["summary"] == "[Max] Jira Publish Idea"
    assert payload["project_key"] == "MAX"
    assert payload["issue_type"] == "Story"
    assert "delivery" in payload["labels"]
    assert "Idea ID: bu-jira001" in payload["description"]
    assert "Publish one approved idea" in payload["description"]
    assert payload["metadata"]["idea_id"] == "bu-jira001"


def test_dry_run_returns_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraIssuePublisher(
        "https://example.atlassian.net",
        "MAX",
        bearer_token="jira_pat",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.issue_key is None
    assert result.issue_url is None
    assert result.payload["metadata"]["idea_id"] == "bu-jira001"


def test_live_publish_posts_jira_issue_with_basic_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "id": "10042",
                "key": "MAX-42",
                "self": "https://example.atlassian.net/rest/api/3/issue/10042",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraIssuePublisher(
        "https://example.atlassian.net",
        "MAX",
        email="agent@example.com",
        api_token="jira_api_token",
        issue_type="Task",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.issue_key == "MAX-42"
    assert result.issue_url == "https://example.atlassian.net/browse/MAX-42"
    assert requests[0].url == "https://example.atlassian.net/rest/api/3/issue"
    expected_auth = base64.b64encode(b"agent@example.com:jira_api_token").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    posted = _json_from_request(requests[0])
    fields = posted["fields"]
    assert fields["project"]["key"] == "MAX"
    assert fields["issuetype"]["name"] == "Task"
    assert fields["summary"] == "[Max] Jira Publish Idea"
    assert fields["description"]["type"] == "doc"
    assert result.payload["metadata"]["jira_issue_key"] == "MAX-42"


def test_live_publish_uses_bearer_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "10042", "key": "MAX-42"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraIssuePublisher(
        "https://example.atlassian.net",
        "MAX",
        bearer_token="jira_bearer",
        client=client,
    )

    publisher.publish(_tact_spec(), dry_run=False)

    assert requests[0].headers["Authorization"] == "Bearer jira_bearer"


def test_live_publish_retries_transient_failures() -> None:
    statuses = [503, 429, 201]
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        status = statuses.pop(0)
        if status == 201:
            return httpx.Response(201, json={"id": "10042", "key": "MAX-42"})
        return httpx.Response(status, json={"error": "try again"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraIssuePublisher(
        "https://example.atlassian.net",
        "MAX",
        bearer_token="jira_bearer",
        max_retries=2,
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.issue_key == "MAX-42"
    assert len(requests) == 3


def test_live_publish_redacts_secrets_in_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="bad token=jira_secret password=jira_password "
            "https://example.atlassian.net/rest/api/3/issue?token=url_secret&safe=yes",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = JiraIssuePublisher(
        "https://example.atlassian.net?token=site_secret",
        "MAX",
        bearer_token="jira_bearer",
        client=client,
    )

    with pytest.raises(JiraIssuePublishError) as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert "jira_secret" not in message
    assert "jira_password" not in message
    assert "url_secret" not in message
    assert "site_secret" not in message
    assert "token=%3Credacted%3E" in message


def test_from_env_reads_jira_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_SITE_URL", "https://env.atlassian.net")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "ENV")
    monkeypatch.setenv("JIRA_EMAIL", "env@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "env_token")

    publisher = JiraIssuePublisher.from_env()

    assert publisher.site_url == "https://env.atlassian.net"
    assert publisher.project_key == "ENV"
    assert publisher.email == "env@example.com"
    assert publisher.api_token == "env_token"


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
