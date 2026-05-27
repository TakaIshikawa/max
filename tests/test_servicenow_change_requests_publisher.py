from __future__ import annotations

import httpx
import pytest

from max.publisher.servicenow_change_requests import ServiceNowChangeRequestPublishError, ServiceNowChangeRequestPublisher
from tests.test_zoom_team_chat_messages_publisher import _spec


def test_dry_run_builds_change_request_payload() -> None:
    result = ServiceNowChangeRequestPublisher(instance_url="https://sn.example", assignment_group="Platform").publish(_spec())
    assert result.payload["endpoint"] == "https://sn.example/api/now/table/change_request"
    assert result.payload["change_request"]["assignment_group"] == "Platform"


def test_live_publish_extracts_result_fields() -> None:
    publisher = ServiceNowChangeRequestPublisher(instance_url="https://sn.example", username="u", password="p", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(201, json={"result": {"sys_id": "sys", "number": "CHG1"}}))))
    result = publisher.publish(_spec(), dry_run=False)
    assert result.sys_id == "sys"
    assert result.number == "CHG1"


def test_http_failure_redacts_password() -> None:
    publisher = ServiceNowChangeRequestPublisher(instance_url="https://sn.example", username="u", password="p", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500, text="bad p"))))
    with pytest.raises(ServiceNowChangeRequestPublishError) as exc:
        publisher.publish(_spec(), dry_run=False)
    assert "bad p" not in str(exc.value)
