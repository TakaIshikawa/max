from __future__ import annotations

import pytest

from max.publisher.confluence_pages import ConfluencePagePublishError, ConfluencePagePublisher


def _brief() -> dict:
    return {"schema_version": "1", "design_brief": {"id": "db1", "title": "Launch Plan", "summary": "Ship it"}}


@pytest.mark.asyncio
async def test_create_payload_uses_deterministic_endpoint_and_parent() -> None:
    publisher = ConfluencePagePublisher("https://conf.example", "ENG", parent_page_id="123")
    result = await publisher.publish(_brief(), dry_run=True)
    assert publisher.page_endpoint == "https://conf.example/wiki/rest/api/content"
    assert result.payload["ancestors"] == [{"id": "123"}]


def test_missing_required_fields_raise() -> None:
    with pytest.raises(ConfluencePagePublishError):
        ConfluencePagePublisher.from_env(site_url="", space_key="")
