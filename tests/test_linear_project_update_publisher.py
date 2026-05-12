from __future__ import annotations

import httpx

from max.publisher.linear_project_updates import (
    LinearProjectUpdatePublishError,
    LinearProjectUpdatePublisher,
)
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_dry_run_returns_linear_graphql_payload() -> None:
    publisher = LinearProjectUpdatePublisher(project_id="proj_123")

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.payload["project_id"] == "proj_123"
    assert "mutation ProjectUpdateCreate" in result.payload["request"]["query"]
    assert "Intercom Conversation Note Publisher" in result.payload["body"]


def test_live_publish_returns_project_update_identifiers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "projectUpdateCreate": {
                        "success": True,
                        "projectUpdate": {"id": "upd_123", "url": "https://linear/update"},
                    }
                }
            },
        )

    publisher = LinearProjectUpdatePublisher(
        project_id="proj_123",
        api_key="lin_key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.update_id == "upd_123"
    assert result.update_url == "https://linear/update"
    assert requests[0].headers["Authorization"] == "lin_key"


def test_graphql_errors_raise_publish_error() -> None:
    publisher = LinearProjectUpdatePublisher(
        project_id="proj_123",
        api_key="lin_key",
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"errors": [{"message": "bad"}]}))),
    )

    try:
        publisher.publish(_tact_spec(), dry_run=False)
    except LinearProjectUpdatePublishError as exc:
        assert exc.status_code == 200
    else:
        raise AssertionError("GraphQL errors should fail publishing")
