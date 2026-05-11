"""Tests for the Mastodon import adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.imports.mastodon_adapter import MastodonImportAdapter
from max.types.signal import SignalSourceType


def _response(payload: object) -> MagicMock:
    response = MagicMock()
    response.json.return_value = payload
    return response


def _status(status_id: str, content: str = "<p>Need better release notes #DevTools</p>") -> dict:
    return {
        "id": status_id,
        "url": f"https://mastodon.example/@ada/{status_id}",
        "created_at": "2026-04-01T12:00:00Z",
        "content": content,
        "account": {"acct": "ada@mastodon.example", "display_name": "Ada"},
        "reblogs_count": 2,
        "favourites_count": 5,
        "tags": [{"name": "DevTools"}],
    }


def test_mastodon_import_adapter_properties() -> None:
    adapter = MastodonImportAdapter(
        config={
            "instance_url": "mastodon.example",
            "tags": ["#DevTools"],
            "query": "ai",
            "access_token_env": "TOKEN_ENV",
        }
    )

    assert adapter.name == "mastodon_import"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert adapter.instance_url == "https://mastodon.example"
    assert adapter.tags == ["DevTools"]
    assert adapter.query == "ai"
    assert adapter.access_token_env == "TOKEN_ENV"


@pytest.mark.asyncio
async def test_fetch_public_tag_statuses_and_deduplicates() -> None:
    adapter = MastodonImportAdapter(config={"instance_url": "https://mastodon.example", "tags": ["devtools"]})
    requested: list[tuple[str, dict]] = []

    async def mock_fetch(url: str, client, *, adapter_name: str, params: dict):
        requested.append((url, params))
        assert adapter_name == "mastodon_import"
        return _response([_status("1"), _status("1"), _status("2", "<p>Second post</p>")])

    with patch("max.imports.mastodon_adapter.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=10)

    assert requested == [
        ("https://mastodon.example/api/v1/timelines/tag/devtools", {"limit": 10})
    ]
    assert [signal.metadata["status_id"] for signal in signals] == ["1", "2"]
    assert signals[0].source_type == SignalSourceType.FORUM
    assert signals[0].source_adapter == "mastodon_import"
    assert signals[0].content == "Need better release notes #DevTools"
    assert signals[0].metadata["favourites"] == 5
    assert signals[0].metadata["reblogs"] == 2
    assert {"mastodon", "fediverse", "community", "devtools"}.issubset(signals[0].tags)


@pytest.mark.asyncio
async def test_fetch_uses_query_when_tags_absent_and_respects_limit() -> None:
    adapter = MastodonImportAdapter(config={"instance_url": "mastodon.example", "query": "roadmap"})

    async def mock_fetch(url: str, client, *, adapter_name: str, params: dict):
        return _response([_status("1"), _status("2")])

    with patch("max.imports.mastodon_adapter.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["query"] == "roadmap"


@pytest.mark.asyncio
async def test_fetch_handles_failures_and_zero_limit() -> None:
    adapter = MastodonImportAdapter(config={"tags": ["devtools"]})

    async def mock_fetch(url: str, client, *, adapter_name: str, params: dict):
        raise RuntimeError("boom")

    with patch("max.imports.mastodon_adapter.fetch_with_retry", mock_fetch):
        assert await adapter.fetch(limit=10) == []
    assert await adapter.fetch(limit=0) == []
