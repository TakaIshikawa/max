from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.notion_page_properties import NotionPagePropertiesPublishError, NotionPagePropertiesPublisher
from tests.test_intercom_conversation_note_publisher import _tact_spec


def test_dry_run_builds_notion_properties_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = NotionPagePropertiesPublisher(page_id="page-123", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_tact_spec(), generated_url="https://max.example.test/specs/1", dry_run=True)

    assert result.dry_run is True
    assert result.endpoint == "https://api.notion.com/v1/pages/page-123"
    assert result.payload["page_id"] == "page-123"
    assert result.payload["properties"]["Name"]["title"][0]["text"]["content"] == "Intercom Conversation Note Publisher"
    assert result.payload["properties"]["Status"]["select"]["name"] == "yes"
    assert result.payload["properties"]["Idea ID"]["rich_text"][0]["text"]["content"] == "bu-intercom001"
    assert result.payload["properties"]["Generated URL"]["url"] == "https://max.example.test/specs/1"
    assert result.payload["metadata"]["publisher"] == "max.notion_page_properties"


def test_live_publish_patches_notion_page_properties() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "page-123", "url": "https://notion.so/page-123"})

    publisher = NotionPagePropertiesPublisher(
        token="notion_token",
        page_id="page-123",
        notion_version="2024-10-01",
        api_url="https://notion.example.test/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), generated_url="https://max.example.test/specs/1", dry_run=False)

    assert result.status_code == 200
    assert result.page_id == "page-123"
    assert result.page_url == "https://notion.so/page-123"
    assert requests[0].method == "PATCH"
    assert requests[0].url == "https://notion.example.test/v1/pages/page-123"
    assert requests[0].headers["Authorization"] == "Bearer notion_token"
    assert requests[0].headers["Notion-Version"] == "2024-10-01"
    posted = json.loads(requests[0].read())
    assert posted["properties"]["Generated URL"]["url"] == "https://max.example.test/specs/1"


def test_custom_property_names_are_supported() -> None:
    publisher = NotionPagePropertiesPublisher(
        page_id="page-123",
        property_names={"title": "Spec", "status": "Decision", "idea_id": "Source", "generated_url": "URL"},
    )

    result = publisher.publish(_tact_spec(), generated_url="https://max.example.test/specs/1", dry_run=True)

    assert set(result.payload["properties"]) == {"Spec", "Decision", "Source", "URL"}
    assert result.payload["properties"]["Decision"]["select"]["name"] == "yes"


def test_from_env_reads_notion_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "env_token")
    monkeypatch.setenv("NOTION_PAGE_ID", "env_page")
    monkeypatch.setenv("NOTION_VERSION", "2024-01-01")
    monkeypatch.setenv("NOTION_API_URL", "https://notion.env.test/v1")

    publisher = NotionPagePropertiesPublisher.from_env()

    assert publisher.token == "env_token"
    assert publisher.page_id == "env_page"
    assert publisher.notion_version == "2024-01-01"
    assert publisher.api_url == "https://notion.env.test/v1"


def test_live_publish_requires_token() -> None:
    publisher = NotionPagePropertiesPublisher(page_id="page-123")

    with pytest.raises(NotionPagePropertiesPublishError, match="NOTION_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_http_error_redacts_notion_token() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"message": "bad Bearer secret_token"}))
    )
    publisher = NotionPagePropertiesPublisher(token="secret_token", page_id="page-123", client=client)

    with pytest.raises(NotionPagePropertiesPublishError, match="HTTP 401") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 401
    assert "secret_token" not in str(exc.value)
    assert "Bearer [REDACTED]" in str(exc.value)
