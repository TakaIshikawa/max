from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.asana_project_status_updates import (
    AsanaProjectStatusUpdatePublishError,
    AsanaProjectStatusUpdatePublisher,
)


def test_dry_run_builds_project_status_update_payload() -> None:
    publisher = AsanaProjectStatusUpdatePublisher("project-123")

    result = publisher.publish(
        title="Launch progress",
        text="Implementation is on track.",
        color="green",
        html_text="<body>Implementation is <strong>on track</strong>.</body>",
        dry_run=True,
    )

    assert result.status_code is None
    assert result.project_gid == "project-123"
    assert result.status_update_gid is None
    assert result.title == "Launch progress"
    assert result.payload["data"]["parent"] == "project-123"
    assert result.payload["data"]["color"] == "green"
    assert result.payload["data"]["html_text"] == "<body>Implementation is <strong>on track</strong>.</body>"
    assert result.payload["metadata"]["publisher"] == "max.asana_project_status_updates"


def test_live_publish_posts_status_update_and_returns_summary() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "data": {
                    "gid": "status-123",
                    "title": "Launch progress",
                    "permalink_url": "https://app.asana.com/0/project-123/status-123",
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = AsanaProjectStatusUpdatePublisher(
        "project-123",
        access_token="asana-token",
        client=client,
    )

    result = publisher.publish(title="Launch progress", text="On track", color="green", dry_run=False)

    assert result.status_code == 201
    assert result.status_update_gid == "status-123"
    assert result.permalink == "https://app.asana.com/0/project-123/status-123"
    assert requests[0].url == "https://app.asana.com/api/1.0/projects/project-123/project_statuses"
    assert requests[0].headers["Authorization"] == "Bearer asana-token"
    posted = json.loads(requests[0].read())
    assert posted == {"data": {"parent": "project-123", "title": "Launch progress", "text": "On track", "color": "green"}}


def test_from_env_reads_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASANA_PROJECT_GID", "project-env")
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "asana-env")

    publisher = AsanaProjectStatusUpdatePublisher.from_env()

    assert publisher.project_gid == "project-env"
    assert publisher.access_token == "asana-env"


def test_live_publish_requires_access_token() -> None:
    publisher = AsanaProjectStatusUpdatePublisher("project-123")

    with pytest.raises(AsanaProjectStatusUpdatePublishError, match="ASANA_ACCESS_TOKEN"):
        publisher.publish(title="Launch progress", text="On track", dry_run=False)
