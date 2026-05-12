from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.figma_dev_resources import FigmaDevResourcePublishError, FigmaDevResourcePublisher
from tests.test_zoom_chat_webhook_publisher import _idea_payload


def test_dry_run_builds_file_level_dev_resource_without_token() -> None:
    publisher = FigmaDevResourcePublisher(file_key="file 123", resource_url="https://max.example/summaries/1", api_url="https://figma.example.test")

    result = publisher.publish(_idea_payload(), dry_run=True)

    resource = result.payload["dev_resources"][0]
    assert result.endpoint == "https://figma.example.test/v1/files/file%20123/dev_resources"
    assert "Authorization" not in result.headers
    assert resource["name"] == "Max summary: Zoom Chat Publisher"
    assert resource["url"] == "https://max.example/summaries/1"
    assert "node_id" not in resource


def test_from_env_reads_figma_dev_resource_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIGMA_ACCESS_TOKEN", "fig-token")
    monkeypatch.setenv("FIGMA_FILE_KEY", "abc123")
    monkeypatch.setenv("FIGMA_NODE_ID", "1:2")
    monkeypatch.setenv("FIGMA_DEV_RESOURCE_NAME", "Max handoff")
    monkeypatch.setenv("FIGMA_DEV_RESOURCE_URL", "https://max.example/handoff")

    publisher = FigmaDevResourcePublisher.from_env()

    assert publisher.access_token == "fig-token"
    assert publisher.file_key == "abc123"
    assert publisher.node_id == "1:2"
    assert publisher.resource_name == "Max handoff"
    assert publisher.resource_url == "https://max.example/handoff"


def test_live_publish_posts_node_level_resource_and_returns_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"dev_resources": [{"id": "res-1", "url": "https://max.example/handoff"}]})

    publisher = FigmaDevResourcePublisher(access_token="fig-token", file_key="abc123", node_id="1:2", resource_name="Max handoff", resource_url="https://max.example/handoff", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.resource_id == "res-1"
    assert result.resource_url == "https://max.example/handoff"
    assert result.headers["Authorization"] == "Bearer [REDACTED]"
    assert requests[0].headers["Authorization"] == "Bearer fig-token"
    posted = json.loads(requests[0].read())["dev_resources"][0]
    assert posted["node_id"] == "1:2"
    assert posted["name"] == "Max handoff"


def test_live_publish_validates_token_file_key_and_resource_url_before_http() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("configuration validation should fail before HTTP")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(FigmaDevResourcePublishError, match="FIGMA_ACCESS_TOKEN"):
        FigmaDevResourcePublisher(file_key="abc123", resource_url="https://max.example", client=client).publish(_idea_payload(), dry_run=False)
    with pytest.raises(ValueError, match="FIGMA_FILE_KEY"):
        FigmaDevResourcePublisher(access_token="fig-token", resource_url="https://max.example", client=client).publish(_idea_payload(), dry_run=False)
    with pytest.raises(ValueError, match="FIGMA_DEV_RESOURCE_URL"):
        FigmaDevResourcePublisher(access_token="fig-token", file_key="abc123", client=client).publish(_idea_payload(), dry_run=False)


def test_live_publish_error_redacts_token() -> None:
    publisher = FigmaDevResourcePublisher(access_token="fig-token", file_key="abc123", resource_url="https://max.example", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, text="bad fig-token"))))

    with pytest.raises(FigmaDevResourcePublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert exc.value.status_code == 401
    assert "fig-token" not in str(exc.value)
