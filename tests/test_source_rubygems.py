"""Tests for the RubyGems source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.rubygems import RubyGemsAdapter, _DEFAULT_QUERIES
from max.types.signal import SignalSourceType


MOCK_SEARCH = [
    {
        "name": "ruby-openai",
        "version": "7.3.1",
        "downloads": 12_345_678,
        "version_downloads": 45_000,
        "info": "Ruby client for OpenAI APIs.",
        "authors": "Alex Developer",
        "project_uri": "https://rubygems.org/gems/ruby-openai",
        "version_created_at": "2026-04-20T12:30:00.000Z",
    },
    {
        "name": "rails-ai",
        "version": "1.2.0",
        "downloads": 250_000,
        "version_downloads": 5_500,
        "info": "AI helpers for Rails apps.",
        "project_uri": "https://rubygems.org/gems/rails-ai",
        "version_created_at": "2026-03-01T08:00:00.000Z",
    },
]

MOCK_DETAILS = {
    "name": "ruby-openai",
    "version": "7.3.1",
    "downloads": 12_345_678,
    "version_downloads": 45_000,
    "info": "Ruby client for OpenAI APIs with chat, embeddings, and streaming support.",
    "authors": "Alex Developer",
    "project_uri": "https://rubygems.org/gems/ruby-openai",
    "gem_uri": "https://rubygems.org/gems/ruby-openai-7.3.1.gem",
    "homepage_uri": "https://github.com/example/ruby-openai",
    "source_code_uri": "https://github.com/example/ruby-openai",
    "documentation_uri": "https://www.rubydoc.info/gems/ruby-openai",
    "bug_tracker_uri": "https://github.com/example/ruby-openai/issues",
    "changelog_uri": "https://github.com/example/ruby-openai/releases",
    "licenses": ["MIT"],
    "version_created_at": "2026-04-20T12:30:00.000Z",
}

MOCK_MINIMAL_SEARCH = [
    {
        "name": "minimal",
        "version": "0.1.0",
        "info": None,
        "downloads": None,
        "version_downloads": None,
    }
]


def test_rubygems_adapter_properties() -> None:
    adapter = RubyGemsAdapter()

    assert adapter.name == "rubygems"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES


def test_rubygems_adapter_custom_config() -> None:
    adapter = RubyGemsAdapter(
        config={"queries": ["rails"], "watchlist_terms": ["sidekiq"], "max_pages": 2}
    )

    assert adapter.queries == ["rails", "sidekiq"]
    assert adapter.max_pages == 2


@pytest.mark.asyncio
async def test_rubygems_adapter_fetches_search_and_details() -> None:
    adapter = RubyGemsAdapter(config={"queries": ["openai"]})

    with patch("max.sources.rubygems.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: [MOCK_SEARCH[0]]),
            MagicMock(json=lambda: MOCK_DETAILS),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_args_list[0].args[0] == "https://rubygems.org/api/v1/search.json"
    assert mock_fetch.call_args_list[0].kwargs["params"] == {"query": "openai", "page": 1}
    assert mock_fetch.call_args_list[1].args[0] == (
        "https://rubygems.org/api/v1/gems/ruby-openai.json"
    )

    signal = signals[0]
    assert signal.id == "rubygems:ruby-openai:7.3.1"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "rubygems"
    assert signal.title == "ruby-openai@7.3.1"
    assert signal.content == (
        "Ruby client for OpenAI APIs with chat, embeddings, and streaming support."
    )
    assert signal.url == "https://rubygems.org/gems/ruby-openai"
    assert signal.author == "Alex Developer"
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert signal.tags == [
        "openai",
        "ruby",
        "rubygems",
        "MIT",
        "package-popularity",
        "release-activity",
        "open-source",
    ]
    assert signal.credibility > 0.8
    assert signal.metadata["package_ecosystem"] == "rubygems"
    assert signal.metadata["gem_name"] == "ruby-openai"
    assert signal.metadata["package_name"] == "ruby-openai"
    assert signal.metadata["version"] == "7.3.1"
    assert signal.metadata["downloads"] == 12_345_678
    assert signal.metadata["download_count"] == 12_345_678
    assert signal.metadata["version_downloads"] == 45_000
    assert signal.metadata["version_created_at"] == "2026-04-20T12:30:00+00:00"
    assert signal.metadata["source_code_uri"] == "https://github.com/example/ruby-openai"
    assert signal.metadata["documentation_uri"] == "https://www.rubydoc.info/gems/ruby-openai"
    assert signal.metadata["search_query"] == "openai"
    assert signal.metadata["signal_kind"] == "package_metadata"


@pytest.mark.asyncio
async def test_rubygems_adapter_respects_limit_without_extra_requests() -> None:
    adapter = RubyGemsAdapter(config={"queries": ["ai", "rails"]})

    with patch("max.sources.rubygems.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_SEARCH),
            MagicMock(json=lambda: MOCK_DETAILS),
        ]

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["gem_name"] == "ruby-openai"
    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[0].kwargs["params"] == {"query": "ai", "page": 1}


@pytest.mark.asyncio
async def test_rubygems_adapter_paginates_until_limit() -> None:
    adapter = RubyGemsAdapter(config={"queries": ["ai"], "max_pages": 2})
    second_details = {
        **MOCK_DETAILS,
        "name": "rails-ai",
        "version": "1.2.0",
        "info": "AI helpers for Rails apps.",
        "downloads": 250_000,
        "version_downloads": 5_500,
        "project_uri": "https://rubygems.org/gems/rails-ai",
        "source_code_uri": None,
        "licenses": ["Apache-2.0"],
        "version_created_at": "2026-03-01T08:00:00.000Z",
    }

    with patch("max.sources.rubygems.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: [MOCK_SEARCH[0]]),
            MagicMock(json=lambda: MOCK_DETAILS),
            MagicMock(json=lambda: [MOCK_SEARCH[1]]),
            MagicMock(json=lambda: second_details),
        ]

        signals = await adapter.fetch(limit=2)

    assert len(signals) == 2
    assert mock_fetch.call_args_list[0].kwargs["params"] == {"query": "ai", "page": 1}
    assert mock_fetch.call_args_list[2].kwargs["params"] == {"query": "ai", "page": 2}
    assert [signal.metadata["gem_name"] for signal in signals] == ["ruby-openai", "rails-ai"]


@pytest.mark.asyncio
async def test_rubygems_adapter_handles_missing_optional_fields() -> None:
    adapter = RubyGemsAdapter(config={"queries": ["minimal"]})

    with patch("max.sources.rubygems.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_MINIMAL_SEARCH),
            MagicMock(json=lambda: {}),
        ]

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "rubygems:minimal:0.1.0"
    assert signal.title == "minimal@0.1.0"
    assert signal.content == "minimal"
    assert signal.url == "https://rubygems.org/gems/minimal"
    assert signal.published_at is None
    assert signal.tags == ["minimal", "ruby", "rubygems"]
    assert signal.credibility == 0.1
    assert signal.metadata["downloads"] == 0
    assert signal.metadata["version_downloads"] is None
    assert signal.metadata["homepage_uri"] is None
    assert signal.metadata["source_code_uri"] is None
