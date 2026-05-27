from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.jira_issue_links import JiraIssueLinkPublishError, JiraIssueLinkPublisher
from tests.test_zoom_team_chat_messages_publisher import _spec


def test_dry_run_returns_issue_link_payload() -> None:
    result = JiraIssueLinkPublisher(base_url="https://jira.example", source_issue_key="MAX-1", target_issue_key="MAX-2").publish(_spec())
    assert result.payload["endpoint"] == "https://jira.example/rest/api/3/issueLink"
    assert result.payload["payload"]["inwardIssue"]["key"] == "MAX-1"


def test_live_publish_posts_with_basic_auth() -> None:
    requests: list[httpx.Request] = []
    publisher = JiraIssueLinkPublisher(base_url="https://jira.example", email="a@example.com", api_token="tok", source_issue_key="MAX-1", target_issue_key="MAX-2", client=httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(201, json={"ok": True}))))
    assert publisher.publish(_spec(), dry_run=False).status_code == 201
    assert json.loads(requests[0].read())["type"]["name"] == "Relates"


def test_errors_validate_keys_and_redact_token() -> None:
    with pytest.raises(JiraIssueLinkPublishError, match="SOURCE"):
        JiraIssueLinkPublisher(base_url="https://jira.example").publish(_spec())
    publisher = JiraIssueLinkPublisher(base_url="https://jira.example", email="a", api_token="tok", source_issue_key="A-1", target_issue_key="A-2", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, text="bad tok"))))
    with pytest.raises(JiraIssueLinkPublishError) as exc:
        publisher.publish(_spec(), dry_run=False)
    assert "tok" not in str(exc.value)
