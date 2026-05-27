from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.asana_task_stories import AsanaTaskStoryPublishError, AsanaTaskStoryPublisher


def test_dry_run_returns_asana_story_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not call Asana")

    publisher = AsanaTaskStoryPublisher(
        task_gid="1200",
        token="asana-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(text="Ship the plan.", html_text="<body>Ship the plan.</body>", dry_run=True)

    assert result.dry_run is True
    assert result.task_gid == "1200"
    assert result.payload["data"] == {
        "text": "Ship the plan.",
        "html_text": "<body>Ship the plan.</body>",
    }
    assert result.payload["request"] == {
        "method": "POST",
        "url": "https://app.asana.com/api/1.0/tasks/1200/stories",
        "headers": {"Authorization": "Bearer asana-token"},
        "json": {"data": {"text": "Ship the plan.", "html_text": "<body>Ship the plan.</body>"}},
    }


def test_publish_posts_story_to_asana_task() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"data": {"gid": "story-1"}})

    publisher = AsanaTaskStoryPublisher(
        task_gid="1200",
        token="asana-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(text="Posted comment.", dry_run=False)

    assert result.status_code == 201
    assert result.story_gid == "story-1"
    assert str(requests[0].url) == "https://app.asana.com/api/1.0/tasks/1200/stories"
    assert requests[0].headers["Authorization"] == "Bearer asana-token"
    assert requests[0].headers["User-Agent"] == "max-asana-task-stories-publisher/1"
    assert json.loads(requests[0].content) == {"data": {"text": "Posted comment."}}


def test_validation_requires_task_gid_and_story_text() -> None:
    publisher = AsanaTaskStoryPublisher()

    with pytest.raises(AsanaTaskStoryPublishError, match="task_gid"):
        publisher.publish(text="Missing task", dry_run=True)

    with pytest.raises(AsanaTaskStoryPublishError, match="text or html_text"):
        AsanaTaskStoryPublisher(task_gid="1200").publish(dry_run=True)
