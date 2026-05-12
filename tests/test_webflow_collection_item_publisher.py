from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.webflow_collection_items import WebflowCollectionItemPublishError, WebflowCollectionItemPublisher, slugify
from tests.test_zoom_chat_webhook_publisher import _design_brief_payload, _idea_payload


def test_maps_idea_payload_to_webflow_field_data() -> None:
    publisher = WebflowCollectionItemPublisher(site_id="site", collection_id="collection")

    result = publisher.publish(_idea_payload(), dry_run=True)

    assert result.endpoint == "https://api.webflow.com/v2/sites/site/collections/collection/items"
    assert result.payload["fieldData"]["name"] == "Zoom Chat Publisher"
    assert result.payload["fieldData"]["slug"] == "bu-zoom001-zoom-chat-publisher"
    assert result.payload["fieldData"]["score"] == "82.0"
    assert result.payload["fieldData"]["recommendation"] == "ship"
    assert result.payload["fieldData"]["domain"] == "devtools"


def test_maps_design_brief_payload_to_webflow_field_data() -> None:
    publisher = WebflowCollectionItemPublisher(site_id="site", collection_id="collection", is_draft=True)

    result = publisher.publish(_design_brief_payload(), dry_run=True)

    assert result.payload["isDraft"] is True
    assert result.payload["fieldData"]["name"] == "Zoom Chat Design Brief"
    assert result.payload["fieldData"]["slug"] == "dbf-zoom001-zoom-chat-design-brief"
    assert result.payload["fieldData"]["readiness-score"] == "88.0"
    assert result.payload["fieldData"]["source-idea-ids"] == "bu-zoom001, bu-supporting"


def test_slugify_is_deterministic_and_url_safe() -> None:
    assert slugify("DBF 001: Zoom Chat Design Brief!") == "dbf-001-zoom-chat-design-brief"
    assert slugify("DBF 001: Zoom Chat Design Brief!") == "dbf-001-zoom-chat-design-brief"


def test_from_env_reads_webflow_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBFLOW_SITE_ID", "site-env")
    monkeypatch.setenv("WEBFLOW_COLLECTION_ID", "collection-env")
    monkeypatch.setenv("WEBFLOW_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WEBFLOW_API_URL", "https://webflow.example.test/v2")

    publisher = WebflowCollectionItemPublisher.from_env()

    assert publisher.site_id == "site-env"
    assert publisher.collection_id == "collection-env"
    assert publisher.access_token == "token"
    assert publisher.api_url == "https://webflow.example.test/v2"


def test_live_publish_posts_item_and_returns_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": "item-1"})

    publisher = WebflowCollectionItemPublisher(site_id="site", collection_id="collection", access_token="token", client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = publisher.publish(_idea_payload(), dry_run=False)

    assert result.item_id == "item-1"
    assert requests[0].headers["Authorization"] == "Bearer token"
    assert json.loads(requests[0].read())["fieldData"]["source-id"] == "bu-zoom001"


def test_webflow_error_redacts_token() -> None:
    publisher = WebflowCollectionItemPublisher(site_id="site", collection_id="collection", access_token="token", client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(400, text="bad token"))))

    with pytest.raises(WebflowCollectionItemPublishError) as exc:
        publisher.publish(_idea_payload(), dry_run=False)

    assert exc.value.status_code == 400
    assert "token" not in str(exc.value)
