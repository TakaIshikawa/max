from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.notion_block_append import NotionBlockAppendPublishError, NotionBlockAppendPublisher
from tests.test_slack_scheduled_message_publisher import _tact_spec


def test_dry_run_builds_children_blocks_with_metadata() -> None:
    publisher = NotionBlockAppendPublisher(block_id="block-123", heading_level=3)

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.block_id == "block-123"
    assert result.endpoint == "https://api.notion.com/v1/blocks/block-123/children"
    children = result.payload["children"]
    assert children[0]["type"] == "heading_3"
    assert children[0]["heading_3"]["rich_text"][0]["text"]["content"] == "Slack Scheduled Message Publisher"
    assert children[1]["type"] == "paragraph"
    assert children[2]["bulleted_list_item"]["rich_text"][0]["text"]["content"].startswith("Evidence:")
    assert children[-1]["type"] == "code"
    assert json.loads(children[-1]["code"]["rich_text"][0]["text"]["content"])["publisher"] == "max.notion_block_append"


def test_live_publish_patches_children_and_returns_appended_ids() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [{"id": "child-1"}, {"id": "child-2"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = NotionBlockAppendPublisher(
        token="notion-token",
        block_id="block-123",
        api_url="https://notion.example.test/v1",
        notion_version="2022-06-28",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 200
    assert result.appended_block_ids == ["child-1", "child-2"]
    assert requests[0].method == "PATCH"
    assert requests[0].url == "https://notion.example.test/v1/blocks/block-123/children"
    assert requests[0].headers["Authorization"] == "Bearer notion-token"
    assert requests[0].headers["Notion-Version"] == "2022-06-28"
    assert json.loads(requests[0].read())["children"][0]["type"] == "heading_2"


def test_from_env_reads_notion_block_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "env-token")
    monkeypatch.setenv("NOTION_BLOCK_ID", "env-block")
    monkeypatch.setenv("NOTION_API_URL", "https://notion.env.test/v1")
    monkeypatch.setenv("NOTION_VERSION", "2025-01-01")

    publisher = NotionBlockAppendPublisher.from_env()

    assert publisher.token == "env-token"
    assert publisher.block_id == "env-block"
    assert publisher.endpoint == "https://notion.env.test/v1/blocks/env-block/children"
    assert publisher.notion_version == "2025-01-01"


def test_validation_http_errors_and_redaction() -> None:
    with pytest.raises(NotionBlockAppendPublishError, match="heading_level"):
        NotionBlockAppendPublisher(block_id="block-123", heading_level=4)

    with pytest.raises(ValueError, match="NOTION_BLOCK_ID"):
        NotionBlockAppendPublisher().publish(_tact_spec())

    with pytest.raises(NotionBlockAppendPublishError, match="NOTION_TOKEN"):
        NotionBlockAppendPublisher(block_id="block-123").publish(_tact_spec(), dry_run=False)

    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403, text="bad token=notion-secret")))
    publisher = NotionBlockAppendPublisher(token="notion-secret", block_id="block-123", client=client)
    with pytest.raises(NotionBlockAppendPublishError, match="HTTP 403") as exc:
        publisher.publish(_tact_spec(), dry_run=False)
    assert "notion-secret" not in str(exc.value)
