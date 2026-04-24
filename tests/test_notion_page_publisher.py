from __future__ import annotations

import httpx
import pytest

from max.publisher.notion_pages import NotionPagePublishError, NotionPagePublisher


def _brief_packet() -> dict:
    return {
        "schema_version": "max.blueprint.source_brief.v1",
        "design_brief": {
            "id": "dbf-notion001",
            "title": "Notion Design Brief",
            "domain": "testing",
            "merged_product_concept": "A shareable workspace page.",
            "synthesis_rationale": "Evidence from customer interviews.",
            "first_milestones": ["Prototype the publisher", "Review with design"],
            "risks": ["Workspace permission drift"],
            "source_idea_ids": ["bu-notion001"],
        },
        "source_ideas": [
            {
                "id": "bu-notion001",
                "role": "lead",
                "problem": "Design briefs are hard to review outside the app.",
                "solution": "Publish the brief into the review workspace.",
                "evidence_rationale": "Three reviewers asked for a collaborative page.",
            }
        ],
    }


def _texts(blocks: list[dict]) -> list[str]:
    texts: list[str] = []
    for block in blocks:
        block_type = block["type"]
        rich_text = block[block_type]["rich_text"]
        texts.extend(item["text"]["content"] for item in rich_text)
    return texts


def test_build_payload_splits_long_markdown_and_preserves_core_sections() -> None:
    publisher = NotionPagePublisher(token="secret", parent_page_id="page-123")
    markdown = "\n".join(
        [
            "# Notion Design Brief",
            "",
            "### Risks",
            "",
            "- Workspace permission drift",
            "",
            "## Long Note",
            "",
            "x" * 4200,
        ]
    )

    payload = publisher.build_payload(_brief_packet(), markdown=markdown).to_dict()
    blocks = payload["page"]["children"] + payload["append_children"]
    texts = _texts(blocks)

    assert all(len(text) <= 1900 for text in texts)
    joined = "\n".join(texts)
    assert "Problem" in joined
    assert "Design briefs are hard to review outside the app." in joined
    assert "Solution" in joined
    assert "Publish the brief into the review workspace." in joined
    assert "Evidence" in joined
    assert "Three reviewers asked for a collaborative page." in joined
    assert "Roadmap" in joined
    assert "Prototype the publisher" in joined
    assert "Risks" in joined


def test_publish_retries_rate_limit_and_returns_page_id_and_url() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                429,
                json={"code": "rate_limited", "message": "Slow down"},
                headers={"retry-after": "0"},
            )
        return httpx.Response(
            200,
            json={"id": "page-created", "url": "https://notion.so/page-created"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = NotionPagePublisher(
        token="secret-token",
        parent_page_id="page-123",
        client=client,
        sleep=lambda _: None,
    )

    result = publisher.publish(_brief_packet(), markdown="# Notion Design Brief")

    assert result.page_id == "page-created"
    assert result.page_url == "https://notion.so/page-created"
    assert result.status_code == 200
    assert result.attempts == 2
    assert len(calls) == 2
    assert calls[0].headers["authorization"] == "Bearer secret-token"


def test_validation_error_is_actionable_and_does_not_echo_token() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                400,
                json={"code": "validation_error", "message": "parent.page_id should be defined"},
            )
        )
    )
    publisher = NotionPagePublisher(
        token="secret-token",
        parent_page_id="page-123",
        client=client,
        sleep=lambda _: None,
    )

    with pytest.raises(NotionPagePublishError) as exc_info:
        publisher.publish(_brief_packet(), markdown="# Brief")

    assert exc_info.value.status_code == 400
    assert "validation_error" in str(exc_info.value)
    assert "parent.page_id should be defined" in str(exc_info.value)
    assert "secret-token" not in str(exc_info.value)
