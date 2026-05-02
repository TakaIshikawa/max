"""Tests for the Stack Overflow tag trends source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.stackoverflow import SE_API
from max.sources.stackoverflow_tag_trends import StackOverflowTagTrendsAdapter
from max.types.signal import SignalSourceType


MOCK_TAGS = [
    {
        "name": "python",
        "count": 2_300_000,
        "last_activity_date": 1_714_608_000,
        "has_synonyms": True,
        "is_moderator_only": False,
        "is_required": False,
    },
    {
        "name": "openai-api",
        "count": 1_234,
        "last_activity_date": 1_714_611_600,
        "has_synonyms": False,
        "is_moderator_only": False,
        "is_required": False,
    },
]


def test_stackoverflow_tag_trends_adapter_properties() -> None:
    adapter = StackOverflowTagTrendsAdapter()

    assert adapter.name == "stackoverflow_tag_trends"
    assert adapter.source_type == SignalSourceType.TRENDING.value
    assert adapter.site == "stackoverflow"
    assert adapter.pagesize == 30
    assert adapter.fromdate is None
    assert adapter.todate is None
    assert adapter.timeout == 30.0
    assert "openai" in adapter.tags


def test_stackoverflow_tag_trends_adapter_custom_config() -> None:
    adapter = StackOverflowTagTrendsAdapter(
        config={
            "tags": ["python", "openai-api", "python"],
            "watchlist_terms": ["langchain"],
            "site": "serverfault",
            "pagesize": 250,
            "fromdate": "1711929600",
            "todate": 1714521600,
            "timeout": "12.5",
        }
    )

    assert adapter.tags == ["python", "openai-api", "langchain"]
    assert adapter.site == "serverfault"
    assert adapter.pagesize == 100
    assert adapter.fromdate == 1_711_929_600
    assert adapter.todate == 1_714_521_600
    assert adapter.timeout == 12.5


@pytest.mark.asyncio
async def test_stackoverflow_tag_trends_fetches_and_normalizes_tag_signals() -> None:
    adapter = StackOverflowTagTrendsAdapter(
        config={
            "tags": ["python", "openai-api"],
            "pagesize": 10,
            "fromdate": 1_711_929_600,
            "todate": 1_714_521_600,
        }
    )

    with patch("max.sources.stackoverflow_tag_trends._get_api_key", return_value=None), \
         patch("max.sources.stackoverflow_tag_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"items": MOCK_TAGS})

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 2
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.args[0] == f"{SE_API}/tags/python;openai-api/info"
    assert mock_fetch.call_args.kwargs["adapter_name"] == "stackoverflow_tag_trends"
    assert mock_fetch.call_args.kwargs["params"] == {
        "site": "stackoverflow",
        "pagesize": 5,
        "fromdate": 1_711_929_600,
        "todate": 1_714_521_600,
    }

    first = signals[0]
    assert first.id == "stackoverflow_tag_trends:stackoverflow:python"
    assert first.source_type == SignalSourceType.TRENDING
    assert first.source_adapter == "stackoverflow_tag_trends"
    assert first.title == "Stack Overflow tag trend: python"
    assert "2,300,000 questions" in first.content
    assert first.url == "https://stackoverflow.com/questions/tagged/python"
    assert first.published_at == datetime(2024, 5, 2, 0, 0, tzinfo=timezone.utc)
    assert first.tags == ["stackoverflow", "stackexchange", "python"]
    assert first.credibility == 1.0
    assert first.metadata["signal_role"] == "market"
    assert first.metadata["site"] == "stackoverflow"
    assert first.metadata["tag"] == "python"
    assert first.metadata["configured_tags"] == ["python", "openai-api"]
    assert first.metadata["question_count"] == 2_300_000
    assert first.metadata["last_activity_date"] == 1_714_608_000
    assert first.metadata["source_url"] == "https://stackoverflow.com/questions/tagged/python"
    assert first.metadata["fromdate"] == 1_711_929_600
    assert first.metadata["todate"] == 1_714_521_600
    assert first.metadata["has_synonyms"] is True


@pytest.mark.asyncio
async def test_stackoverflow_tag_trends_uses_api_key_limit_and_encoded_tags() -> None:
    adapter = StackOverflowTagTrendsAdapter(config={"tags": ["c#", "go"], "pagesize": 50})

    with patch("max.sources.stackoverflow_tag_trends._get_api_key", return_value="secret"), \
         patch("max.sources.stackoverflow_tag_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"items": MOCK_TAGS})

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == f"{SE_API}/tags/c%23;go/info"
    assert mock_fetch.call_args.kwargs["params"] == {
        "site": "stackoverflow",
        "pagesize": 1,
        "key": "secret",
    }


@pytest.mark.asyncio
async def test_stackoverflow_tag_trends_deduplicates_and_handles_bad_payloads() -> None:
    adapter = StackOverflowTagTrendsAdapter(config={"tags": ["python"]})
    payload = [
        MOCK_TAGS[0],
        {**MOCK_TAGS[0], "count": 999},
        {"count": 10},
        "not-a-dict",
    ]

    with patch("max.sources.stackoverflow_tag_trends._get_api_key", return_value=None), \
         patch("max.sources.stackoverflow_tag_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"items": payload})

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["question_count"] == 2_300_000

    with patch("max.sources.stackoverflow_tag_trends._get_api_key", return_value=None), \
         patch("max.sources.stackoverflow_tag_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"items": {"not": "a list"}})

        signals = await adapter.fetch(limit=10)

    assert signals == []

    with patch("max.sources.stackoverflow_tag_trends._get_api_key", return_value=None), \
         patch("max.sources.stackoverflow_tag_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = RuntimeError("boom")

        signals = await adapter.fetch(limit=10)

    assert signals == []
