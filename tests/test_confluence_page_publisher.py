"""Tests for Confluence page publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher import ConfluencePagePublisher
from max.publisher.confluence_pages import ConfluencePagePublishError


def _brief_packet() -> dict:
    return {
        "schema_version": "max.blueprint.source_brief.v1",
        "design_brief": {
            "id": "dbf-confluence001",
            "title": "Confluence Design Brief",
            "domain": "design-ops",
            "merged_product_concept": "A shared design brief page for reviewers.",
            "synthesis_rationale": "Reviewers already use Confluence for decisions.",
            "first_milestones": ["Create page publisher", "Run one pilot review"],
            "risks": ["Space permissions may block publication"],
            "source_idea_ids": ["bu-confluence001"],
        },
        "source_ideas": [
            {
                "id": "bu-confluence001",
                "role": "lead",
                "problem": "Validated briefs are hard to discuss in existing team rituals.",
                "solution": "Publish structured briefs into the design workspace.",
                "evidence_rationale": "Design leads requested a collaborative artifact.",
            }
        ],
    }


def test_build_page_payload_maps_design_brief_fields() -> None:
    publisher = ConfluencePagePublisher(
        "https://example.atlassian.net",
        "MAX",
        parent_page_id="12345",
    )

    payload = publisher.build_page_payload(_brief_packet()).to_dict()

    assert payload["type"] == "page"
    assert payload["title"] == "Confluence Design Brief"
    assert payload["space"]["key"] == "MAX"
    assert payload["ancestors"] == [{"id": "12345"}]
    assert payload["body"]["storage"]["representation"] == "storage"
    body = payload["body"]["storage"]["value"]
    assert "Validated briefs are hard to discuss" in body
    assert "Publish structured briefs" in body
    assert "Create page publisher" in body
    assert "Space permissions may block publication" in body
    assert payload["metadata"]["design_brief_id"] == "dbf-confluence001"


@pytest.mark.asyncio
async def test_dry_run_returns_payload_without_network_call() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = ConfluencePagePublisher(
        "https://example.atlassian.net",
        "MAX",
        parent_page_id="12345",
        bearer_token="confluence_bearer",
        client=client,
    )

    result = await publisher.publish(_brief_packet(), dry_run=True)
    await client.aclose()

    assert result.dry_run is True
    assert result.status_code is None
    assert result.page_id is None
    assert result.page_url is None
    assert result.payload["title"] == "Confluence Design Brief"
    assert result.payload["space"]["key"] == "MAX"


@pytest.mark.asyncio
async def test_live_publish_posts_confluence_content_with_basic_auth() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"id": "98765", "_links": {"webui": "/wiki/spaces/MAX/pages/98765/Brief"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = ConfluencePagePublisher(
        "https://example.atlassian.net",
        "MAX",
        parent_page_id="12345",
        email="agent@example.com",
        api_token="api-token",
        client=client,
    )

    result = await publisher.publish(_brief_packet(), dry_run=False)
    await client.aclose()

    assert result.status_code == 200
    assert result.page_id == "98765"
    assert result.page_url == "https://example.atlassian.net/wiki/spaces/MAX/pages/98765/Brief"
    assert requests[0].url == "https://example.atlassian.net/wiki/rest/api/content"
    expected_auth = base64.b64encode(b"agent@example.com:api-token").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    posted = json.loads(requests[0].read())
    assert posted["type"] == "page"
    assert posted["title"] == "Confluence Design Brief"
    assert posted["space"]["key"] == "MAX"
    assert posted["ancestors"] == [{"id": "12345"}]
    assert posted["body"]["storage"]["representation"] == "storage"
    assert "Design leads requested" in posted["body"]["storage"]["value"]


@pytest.mark.asyncio
async def test_live_publish_raises_contextual_error_for_http_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "Current user cannot create content in this space"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    publisher = ConfluencePagePublisher(
        "https://example.atlassian.net",
        "MAX",
        parent_page_id="12345",
        bearer_token="confluence_bearer",
        client=client,
    )

    with pytest.raises(ConfluencePagePublishError) as exc:
        await publisher.publish(_brief_packet(), dry_run=False)
    await client.aclose()

    assert exc.value.status_code == 403
    assert "HTTP 403" in str(exc.value)
    assert "Current user cannot create content" in str(exc.value)


def test_from_env_reads_confluence_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_SITE_URL", "https://env.atlassian.net")
    monkeypatch.setenv("CONFLUENCE_SPACE_KEY", "ENV")
    monkeypatch.setenv("CONFLUENCE_PARENT_PAGE_ID", "24680")
    monkeypatch.setenv("CONFLUENCE_EMAIL", "env@example.com")
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "env-token")

    publisher = ConfluencePagePublisher.from_env()

    assert publisher.site_url == "https://env.atlassian.net"
    assert publisher.space_key == "ENV"
    assert publisher.parent_page_id == "24680"
    assert publisher.email == "env@example.com"
    assert publisher.api_token == "env-token"
