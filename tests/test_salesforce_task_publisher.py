from __future__ import annotations

import json

import httpx

from max.publisher.salesforce_tasks import SalesforceTaskPublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_builds_salesforce_task_payload_with_optional_fields() -> None:
    publisher = SalesforceTaskPublisher(status="Open", priority="High", owner_id="005", what_id="006", who_id="003")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.endpoint == "/services/data/v60.0/sobjects/Task"
    assert result.payload["Subject"] == "Max follow-up: Zoom Chat Publisher"
    assert result.payload["Status"] == "Open"
    assert result.payload["Priority"] == "High"
    assert result.payload["OwnerId"] == "005"
    assert "Idea ID: bu-zoom001" in result.payload["Description"]


def test_from_env_reads_salesforce_task_configuration(monkeypatch) -> None:
    monkeypatch.setenv("SALESFORCE_INSTANCE_URL", "https://salesforce.example.test")
    monkeypatch.setenv("SALESFORCE_ACCESS_TOKEN", "sf-token")
    monkeypatch.setenv("SALESFORCE_API_VERSION", "v61.0")
    monkeypatch.setenv("SALESFORCE_TASK_OWNER_ID", "005")

    publisher = SalesforceTaskPublisher.from_env()

    assert publisher.instance_url == "https://salesforce.example.test"
    assert publisher.access_token == "sf-token"
    assert publisher.api_version == "v61.0"
    assert publisher.owner_id == "005"


def test_live_publish_posts_task_and_returns_created_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "00T1"})

    publisher = SalesforceTaskPublisher(instance_url="https://salesforce.example.test", access_token="sf-token", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.task_id == "00T1"
    assert result.task_url == "https://salesforce.example.test/00T1"
    assert requests[0].headers["Authorization"] == "Bearer sf-token"
    assert "metadata" not in json.loads(requests[0].read())
