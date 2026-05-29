from __future__ import annotations

import httpx

from max.publisher.asana_task_comments import AsanaTaskCommentPublisher


def test_rejects_missing_task_or_text() -> None:
    publisher = AsanaTaskCommentPublisher()
    try:
        publisher.publish(text="hello")
    except Exception as exc:
        assert "task_gid" in str(exc)
    try:
        AsanaTaskCommentPublisher(task_gid="1").publish(text=" ")
    except Exception as exc:
        assert "text" in str(exc)


def test_dry_run_returns_target_and_payload_without_network() -> None:
    publisher = AsanaTaskCommentPublisher(task_gid="1", client=httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError()))))
    result = publisher.publish(text=" hello ", is_pinned=True)
    assert result.payload["endpoint"].endswith("/tasks/1/stories")
    assert result.payload["payload"]["data"] == {"text": "hello", "is_pinned": True}


def test_api_failure_returns_deterministic_failure_structure() -> None:
    publisher = AsanaTaskCommentPublisher(task_gid="1", access_token="tok", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(400, text="bad tok"))))
    result = publisher.publish(text="hello", dry_run=False)
    assert result.status_code == 400
    assert result.payload["error"] == "bad [REDACTED]"
