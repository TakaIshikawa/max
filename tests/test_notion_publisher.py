from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.notion_database import NotionDatabasePublisher


def _unit() -> dict:
    return {
        "id": "bu-notion001",
        "title": "Review Queue Assistant",
        "status": "approved",
        "score": 87.5,
        "category": ["automation", "workflow"],
        "problem_statement": "Product teams lose track of approved ideas.",
        "solution_approach": "Create a Notion-backed idea review queue.",
        "tech_stack": ["FastAPI", "Notion API", "PostgreSQL"],
    }


def test_build_payload_maps_buildable_unit_to_notion_properties() -> None:
    publisher = NotionDatabasePublisher(token="secret", database_id="db-123")

    payload = publisher.build_payload(_unit()).to_dict()
    properties = payload["properties"]

    assert payload["parent"] == {"database_id": "db-123"}
    assert properties["Title"]["title"][0]["text"]["content"] == "Review Queue Assistant"
    assert properties["Status"] == {"select": {"name": "approved"}}
    assert properties["Score"] == {"number": 87.5}
    assert properties["Category"]["multi_select"] == [
        {"name": "automation"},
        {"name": "workflow"},
    ]
    assert (
        properties["Problem Statement"]["rich_text"][0]["text"]["content"]
        == "Product teams lose track of approved ideas."
    )
    assert (
        properties["Solution Approach"]["rich_text"][0]["text"]["content"]
        == "Create a Notion-backed idea review queue."
    )
    assert properties["Tech Stack"]["multi_select"] == [
        {"name": "FastAPI"},
        {"name": "Notion API"},
        {"name": "PostgreSQL"},
    ]
    assert payload["metadata"]["unit_id"] == "bu-notion001"


def test_publish_creates_notion_page_and_returns_summary() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "page-123",
                "url": "https://notion.so/page-123",
                "created_time": "2026-05-12T00:00:00.000Z",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = NotionDatabasePublisher(token="secret-token", database_id="db-123", client=client)

    result = publisher.publish(_unit())

    assert result == {
        "id": "page-123",
        "url": "https://notion.so/page-123",
        "created_time": "2026-05-12T00:00:00.000Z",
    }
    assert requests[0].url == "https://api.notion.com/v1/pages"
    assert requests[0].headers["authorization"] == "Bearer secret-token"
    assert requests[0].headers["notion-version"] == "2022-06-28"
    posted = json.loads(requests[0].read())
    assert posted["parent"] == {"database_id": "db-123"}
    assert posted["properties"]["Title"]["title"][0]["text"]["content"] == "Review Queue Assistant"


def test_publish_retries_rate_limit_with_retry_after() -> None:
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                json={"code": "rate_limited", "message": "Slow down"},
                headers={"Retry-After": "1.5"},
            )
        return httpx.Response(
            200,
            json={
                "id": "page-after-retry",
                "url": "https://notion.so/page-after-retry",
                "created_time": "2026-05-12T00:01:00.000Z",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = NotionDatabasePublisher(
        token="secret-token",
        database_id="db-123",
        client=client,
        max_retries=1,
        sleep=sleeps.append,
    )

    result = publisher.publish(_unit())

    assert result["id"] == "page-after-retry"
    assert len(requests) == 2
    assert sleeps == [1.5]


def test_missing_credentials_raise_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTION_API_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_DATABASE_ID", raising=False)

    with pytest.raises(ValueError, match="NOTION_API_TOKEN"):
        NotionDatabasePublisher()

    with pytest.raises(ValueError, match="NOTION_DATABASE_ID"):
        NotionDatabasePublisher(token="secret-token")
