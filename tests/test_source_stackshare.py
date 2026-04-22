"""Tests for the StackShare source adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.sources.stackshare import (
    DEFAULT_BASE_URL,
    StackShareAdapter,
    _DEFAULT_CATEGORIES,
    _DEFAULT_STACKS,
    _credibility,
)
from max.types.signal import SignalSourceType


MOCK_STACK = {
    "tools": [
        {
            "tool": {
                "name": "PostgreSQL",
                "slug": "postgresql",
                "description": "A powerful open source object-relational database system.",
                "category": {"name": "Databases"},
                "stacks_count": 70_000,
                "users_count": 180_000,
                "alternatives": [{"name": "MySQL"}, {"name": "MongoDB"}],
                "stackshare_url": "https://stackshare.io/postgresql",
            }
        }
    ]
}


def test_stackshare_adapter_properties() -> None:
    adapter = StackShareAdapter()

    assert adapter.name == "stackshare"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.base_url == DEFAULT_BASE_URL
    assert adapter.stacks == _DEFAULT_STACKS
    assert adapter.categories == _DEFAULT_CATEGORIES


def test_stackshare_adapter_custom_config() -> None:
    adapter = StackShareAdapter(
        config={
            "base_url": "https://stackshare.example.test/api/",
            "stacks": ["acme"],
            "categories": ["databases"],
            "watchlist_terms": ["observability"],
        }
    )

    assert adapter.base_url == "https://stackshare.example.test/api"
    assert adapter.stacks == ["acme", "observability"]
    assert adapter.categories == ["databases", "observability"]


@pytest.mark.asyncio
async def test_stackshare_fetch_success() -> None:
    adapter = StackShareAdapter(config={"stacks": ["acme"], "categories": []})

    with patch("max.sources.stackshare.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_STACK)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == "https://stackshare.io/api/v1/stacks/acme"
    assert mock_fetch.call_args.kwargs["params"] == {"limit": 5}

    signal = signals[0]
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "stackshare"
    assert signal.title == "PostgreSQL"
    assert signal.content == "A powerful open source object-relational database system."
    assert signal.url == "https://stackshare.io/postgresql"
    assert signal.tags == ["Databases", "acme", "MySQL", "MongoDB"]
    assert signal.credibility > 0.9
    assert signal.metadata["tool_name"] == "PostgreSQL"
    assert signal.metadata["description"] == "A powerful open source object-relational database system."
    assert signal.metadata["category"] == "Databases"
    assert signal.metadata["company_adoption_count"] == 70_000
    assert signal.metadata["user_adoption_count"] == 180_000
    assert signal.metadata["alternatives"] == ["MySQL", "MongoDB"]
    assert signal.metadata["source_url"] == "https://stackshare.io/postgresql"
    assert signal.metadata["stack"] == "acme"


def test_stackshare_credibility_scales_from_adoption_counts() -> None:
    low = _credibility(company_adoption_count=5, user_adoption_count=20)
    high = _credibility(
        company_adoption_count=50_000,
        user_adoption_count=200_000,
        alternatives=["MySQL"],
    )

    assert low < high
    assert high > 0.9
    assert _credibility(company_adoption_count=0, user_adoption_count=0) == 0.4


@pytest.mark.asyncio
async def test_stackshare_deduplicates_tools_across_requests() -> None:
    adapter = StackShareAdapter(config={"stacks": ["acme"], "categories": ["databases"]})
    category_listing = {
        "tools": [
            {
                "name": "PostgreSQL",
                "slug": "postgresql",
                "description": "Duplicate database.",
            },
            {
                "name": "Redis",
                "slug": "redis",
                "description": "In-memory data store.",
                "category": "Databases",
            },
        ]
    }

    with patch("max.sources.stackshare.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_STACK),
            MagicMock(json=lambda: category_listing),
        ]

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["tool_name"] for signal in signals] == ["PostgreSQL", "Redis"]
    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_stackshare_respects_limit() -> None:
    adapter = StackShareAdapter(config={"stacks": ["acme"], "categories": ["databases"]})
    listing = {
        "tools": [
            {"name": "PostgreSQL", "slug": "postgresql", "description": "Database."},
            {"name": "Redis", "slug": "redis", "description": "Cache."},
        ]
    }

    with patch("max.sources.stackshare.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: listing)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["tool_name"] == "PostgreSQL"
    assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_stackshare_handles_missing_optional_fields() -> None:
    adapter = StackShareAdapter(config={"stacks": [], "categories": ["devops"]})
    listing = {"items": [{"name": "Nomad"}]}

    with patch("max.sources.stackshare.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: listing)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "Nomad"
    assert signal.content == "Nomad"
    assert signal.url == "https://stackshare.io/api/v1/tools/nomad"
    assert signal.tags == ["devops"]
    assert signal.credibility == 0.4
    assert signal.metadata["category"] == "devops"
    assert signal.metadata["company_adoption_count"] == 0
    assert signal.metadata["user_adoption_count"] == 0
    assert signal.metadata["alternatives"] == []
    assert signal.metadata["source_url"] == signal.url
