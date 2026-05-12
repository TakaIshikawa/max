from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.gitlab_notes import GitLabNotePublishError, GitLabNotePublisher
from tests.test_zoom_chat_webhook_publisher import _design_brief_payload, _idea_payload


def test_builds_issue_note_endpoint_and_idea_body() -> None:
    publisher = GitLabNotePublisher(project_id="group/project", resource_type="issue", resource_iid="7")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.endpoint == "https://gitlab.com/api/v4/projects/group%2Fproject/issues/7/notes"
    assert "## Zoom Chat Publisher" in result.body
    assert "Source ID: bu-zoom001" in result.body
    assert "insights=ins-zoom001" in result.body


def test_builds_merge_request_and_epic_endpoints() -> None:
    mr = GitLabNotePublisher(project_id="42", resource_type="merge_request", resource_iid="8")
    epic = GitLabNotePublisher(project_id="group", resource_type="epic", resource_iid="9")

    assert mr.notes_endpoint() == "https://gitlab.com/api/v4/projects/42/merge_requests/8/notes"
    assert epic.notes_endpoint() == "https://gitlab.com/api/v4/groups/group/epics/9/notes"


def test_builds_design_brief_body() -> None:
    publisher = GitLabNotePublisher(project_id="42", resource_iid="7")

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    assert "## Zoom Chat Design Brief" in result.body
    assert "Readiness score: 88.0" in result.body
    assert "bu-zoom001, bu-supporting" in result.body


def test_from_env_reads_gitlab_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_PROJECT_ID", "env/project")
    monkeypatch.setenv("GITLAB_RESOURCE_TYPE", "merge_request")
    monkeypatch.setenv("GITLAB_RESOURCE_IID", "11")
    monkeypatch.setenv("GITLAB_PRIVATE_TOKEN", "token")
    monkeypatch.setenv("GITLAB_API_URL", "https://gitlab.example.test/api/v4")

    publisher = GitLabNotePublisher.from_env()

    assert publisher.project_id == "env/project"
    assert publisher.resource_type == "merge_request"
    assert publisher.resource_iid == "11"
    assert publisher.token == "token"
    assert publisher.api_url == "https://gitlab.example.test/api/v4"


def test_live_publish_posts_note_and_returns_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 123})

    publisher = GitLabNotePublisher(project_id="42", resource_iid="7", token="token", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.note_id == "123"
    assert requests[0].headers["PRIVATE-TOKEN"] == "token"
    assert "Zoom Chat Publisher" in json.loads(requests[0].read())["body"]


def test_gitlab_error_redacts_token() -> None:
    publisher = GitLabNotePublisher(project_id="42", resource_iid="7", token="token", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(400, text="bad token"))))

    with pytest.raises(GitLabNotePublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert exc.value.status_code == 400
    assert "token" not in str(exc.value)
