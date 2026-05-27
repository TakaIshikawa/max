from __future__ import annotations

import httpx
import pytest

from max.publisher.linear_project_updates import LinearProjectUpdatePublishError, LinearProjectUpdatePublisher
from tests.test_zoom_team_chat_messages_publisher import _spec


def test_dry_run_includes_graphql_variables() -> None:
    result = LinearProjectUpdatePublisher(project_id="proj", health="atRisk", status="planned").publish(_spec())
    variables = result.payload["request"]["variables"]["input"]
    assert variables["projectId"] == "proj"
    assert variables["health"] == "atRisk"
    assert "Zoom Chat Publisher" in variables["title"]


def test_live_publish_extracts_update_id() -> None:
    requests: list[httpx.Request] = []
    publisher = LinearProjectUpdatePublisher(project_id="proj", api_key="key", client=httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200, json={"data": {"projectUpdateCreate": {"projectUpdate": {"id": "upd", "url": "u"}}}}))))
    assert publisher.publish(_spec(), dry_run=False).update_id == "upd"
    assert requests[0].headers["Authorization"] == "Bearer key"


def test_graphql_errors_raise() -> None:
    publisher = LinearProjectUpdatePublisher(project_id="proj", api_key="key", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"errors": [{"message": "bad key"}]}))))
    with pytest.raises(LinearProjectUpdatePublishError):
        publisher.publish(_spec(), dry_run=False)
