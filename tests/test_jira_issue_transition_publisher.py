from __future__ import annotations

import json

import httpx

from max.publisher.jira_issue_transitions import JiraIssueTransitionPublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_resolves_transition_endpoint_and_payload_with_comment() -> None:
    publisher = JiraIssueTransitionPublisher(base_url="https://jira.example.test", issue_key="MAX-1", transition_id="31", comment="Ready to ship")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.endpoint == "https://jira.example.test/rest/api/3/issue/MAX-1/transitions"
    assert result.payload["transition"] == {"id": "31"}
    assert result.payload["update"]["comment"][0]["add"]["body"]["content"][0]["content"][0]["text"] == "Ready to ship"


def test_from_env_reads_jira_transition_configuration(monkeypatch) -> None:
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example.test")
    monkeypatch.setenv("JIRA_EMAIL", "dev@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "jira-token")
    monkeypatch.setenv("JIRA_ISSUE_KEY", "MAX-2")
    monkeypatch.setenv("JIRA_TRANSITION_ID", "41")
    monkeypatch.setenv("JIRA_TRANSITION_COMMENT", "Done")

    publisher = JiraIssueTransitionPublisher.from_env()

    assert publisher.base_url == "https://jira.example.test"
    assert publisher.email == "dev@example.com"
    assert publisher.api_token == "jira-token"
    assert publisher.issue_key == "MAX-2"
    assert publisher.transition_id == "41"
    assert publisher.comment == "Done"


def test_live_publish_sends_basic_auth_and_accepts_empty_success() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    publisher = JiraIssueTransitionPublisher(base_url="https://jira.example.test", email="dev@example.com", api_token="jira-token", issue_key="MAX-1", transition_id="31", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.status_code == 204
    assert requests[0].headers["Authorization"].startswith("Basic ")
    assert json.loads(requests[0].read())["transition"]["id"] == "31"
