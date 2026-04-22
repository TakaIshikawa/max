"""Tests for the Crates.io source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.crates_io import CratesIoAdapter, _DEFAULT_CATEGORIES, _DEFAULT_QUERIES
from max.types.signal import SignalSourceType


MOCK_SEARCH = {
    "crates": [
        {
            "id": "tokio",
            "name": "tokio",
            "max_version": "1.48.0",
            "description": "An event-driven platform for asynchronous I/O.",
            "downloads": 500_000_000,
            "recent_downloads": 25_000_000,
            "updated_at": "2026-04-20T12:30:00Z",
            "repository": "https://github.com/tokio-rs/tokio",
            "homepage": "https://tokio.rs",
            "documentation": "https://docs.rs/tokio",
            "keywords": ["async", "io"],
            "categories": ["asynchronous"],
        },
        {
            "id": "serde",
            "name": "serde",
            "max_version": "1.0.228",
            "description": "Serialization framework",
            "downloads": 600_000_000,
            "recent_downloads": 30_000_000,
            "updated_at": "2026-04-18T08:00:00Z",
            "repository": "https://github.com/serde-rs/serde",
            "keywords": ["serde"],
            "categories": ["encoding"],
        },
    ]
}

MOCK_CATEGORY = {
    "crates": [
        {
            "id": "clap",
            "name": "clap",
            "newest_version": "4.5.50",
            "description": "Command line argument parser",
            "downloads": 250_000_000,
            "recent_downloads": 10_000_000,
            "updated_at": "2026-04-19T09:00:00Z",
            "repository": "https://github.com/clap-rs/clap",
            "categories": ["command-line-interface"],
        }
    ]
}

MOCK_MISSING_OPTIONAL = {
    "crates": [
        {
            "id": "minimal",
            "name": "minimal",
            "description": None,
            "downloads": None,
            "recent_downloads": None,
        }
    ]
}


def test_crates_io_adapter_properties() -> None:
    adapter = CratesIoAdapter()

    assert adapter.name == "crates_io"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.categories == _DEFAULT_CATEGORIES


def test_crates_io_adapter_custom_config() -> None:
    adapter = CratesIoAdapter(
        config={
            "queries": ["webassembly"],
            "categories": ["wasm"],
            "watchlist_terms": ["embedded"],
        }
    )

    assert adapter.queries == ["webassembly", "embedded"]
    assert adapter.categories == ["wasm", "embedded"]


@pytest.mark.asyncio
async def test_crates_io_adapter_fetch_success() -> None:
    adapter = CratesIoAdapter(config={"queries": ["async"], "categories": []})

    with patch("max.sources.crates_io.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_SEARCH)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.kwargs["params"] == {"q": "async", "per_page": 10}

    first = signals[0]
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "crates_io"
    assert first.title == "tokio@1.48.0"
    assert first.content == "An event-driven platform for asynchronous I/O."
    assert first.url == "https://crates.io/crates/tokio"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.tags == ["async", "io", "asynchronous"]
    assert first.credibility > 0.8
    assert first.metadata["crate_name"] == "tokio"
    assert first.metadata["version"] == "1.48.0"
    assert first.metadata["downloads"] == 500_000_000
    assert first.metadata["recent_downloads"] == 25_000_000
    assert first.metadata["repository"] == "https://github.com/tokio-rs/tokio"
    assert first.metadata["homepage"] == "https://tokio.rs"
    assert first.metadata["documentation"] == "https://docs.rs/tokio"
    assert first.metadata["search_query"] == "async"


@pytest.mark.asyncio
async def test_crates_io_adapter_respects_limit_across_queries_and_categories() -> None:
    adapter = CratesIoAdapter(config={"queries": ["async"], "categories": ["cli"]})

    with patch("max.sources.crates_io.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_SEARCH)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["crate_name"] == "tokio"
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.kwargs["params"]["per_page"] == 1


@pytest.mark.asyncio
async def test_crates_io_adapter_fetches_configured_categories() -> None:
    adapter = CratesIoAdapter(config={"queries": [], "categories": ["command-line-utilities"]})

    with patch("max.sources.crates_io.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_CATEGORY)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert "categories/command-line-utilities/crates" in mock_fetch.call_args.args[0]
    assert signals[0].title == "clap@4.5.50"
    assert signals[0].metadata["category"] == "command-line-utilities"
    assert signals[0].metadata["repository"] == "https://github.com/clap-rs/clap"


@pytest.mark.asyncio
async def test_crates_io_adapter_handles_missing_optional_fields() -> None:
    adapter = CratesIoAdapter(config={"queries": ["minimal"], "categories": []})

    with patch("max.sources.crates_io.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_MISSING_OPTIONAL)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "minimal"
    assert signal.content == "minimal"
    assert signal.published_at is None
    assert signal.credibility == 0.1
    assert signal.metadata["downloads"] == 0
    assert signal.metadata["recent_downloads"] is None
    assert signal.metadata["repository"] is None
    assert signal.metadata["homepage"] is None
    assert signal.metadata["documentation"] is None
