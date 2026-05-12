from __future__ import annotations

import json

import httpx

from max.publisher.gitlab_pipeline_triggers import GitLabPipelineTriggerPublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_builds_pipeline_trigger_payload() -> None:
    publisher = GitLabPipelineTriggerPublisher(project_id="group/project", ref="main", trigger_token="secret", variables={"EXTRA": "1"}, api_url="https://gitlab.example/api/v4")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.endpoint == "https://gitlab.example/api/v4/projects/group%2Fproject/trigger/pipeline"
    assert result.payload["ref"] == "main"
    assert result.payload["token"] == "[REDACTED]"
    assert result.payload["variables"]["EXTRA"] == "1"
    assert result.payload["variables"]["MAX_TITLE"] == "Zoom Chat Publisher"
    assert "Zoom Chat Publisher" in result.payload["variables"]["MAX_SUMMARY"]


def test_from_env_reads_gitlab_pipeline_trigger_configuration(monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_PROJECT_ID", "123")
    monkeypatch.setenv("GITLAB_REF", "release")
    monkeypatch.setenv("GITLAB_TRIGGER_TOKEN", "trigger-token")
    monkeypatch.setenv("GITLAB_API_URL", "https://gitlab.example/api/v4")

    publisher = GitLabPipelineTriggerPublisher.from_env()

    assert publisher.project_id == "123"
    assert publisher.ref == "release"
    assert publisher.trigger_token == "trigger-token"
    assert publisher.api_url == "https://gitlab.example/api/v4"


def test_live_publish_posts_json_and_returns_pipeline_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 42, "web_url": "https://gitlab.example/pipelines/42"})

    publisher = GitLabPipelineTriggerPublisher(project_id="123", ref="main", trigger_token="trigger-token", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.status_code == 201
    assert result.pipeline_id == "42"
    assert result.web_url == "https://gitlab.example/pipelines/42"
    assert result.payload["token"] == "[REDACTED]"
    assert json.loads(requests[0].read())["token"] == "trigger-token"


