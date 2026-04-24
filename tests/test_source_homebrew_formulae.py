"""Tests for the Homebrew Formulae source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.homebrew_formulae import (
    HOMEBREW_CASKS_URL,
    HOMEBREW_FORMULAE_URL,
    HomebrewFormulaeAdapter,
)
from max.types.signal import SignalSourceType


MOCK_FORMULAE = [
    {
        "name": "ripgrep",
        "full_name": "ripgrep",
        "tap": "homebrew/core",
        "desc": "Search tool like grep and The Silver Searcher",
        "homepage": "https://github.com/BurntSushi/ripgrep",
        "versions": {"stable": "14.1.1", "head": "HEAD"},
        "dependencies": ["pcre2"],
        "build_dependencies": ["rust"],
        "updated_at": "2026-04-20T12:30:00Z",
        "analytics": {
            "install": {"30d": {"ripgrep": 22000}},
            "install_on_request": {"30d": {"ripgrep": 21000}},
        },
    },
    {
        "name": "uv",
        "tap": "homebrew/core",
        "desc": "Extremely fast Python package installer and resolver",
        "homepage": "https://docs.astral.sh/uv/",
        "versions": {"stable": "0.8.0"},
        "dependencies": [],
        "analytics": {"install": {"30d": {"uv": 18000}}},
    },
]

MOCK_CASKS = [
    {
        "token": "visual-studio-code",
        "tap": "homebrew/cask",
        "name": ["Visual Studio Code"],
        "desc": "Open-source code editor",
        "homepage": "https://code.visualstudio.com/",
        "version": "1.100.0",
        "artifacts": [{"app": ["Visual Studio Code.app"]}, {"binary": [["code"]]}],
        "depends_on": {"macos": [">= :monterey"]},
        "updated_at": "2026-04-18T10:00:00Z",
        "analytics": {"install": {"30d": {"visual-studio-code": 50000}}},
    }
]

MOCK_DUPLICATE_CASKS = [
    {
        "token": "ripgrep",
        "tap": "homebrew/cask",
        "name": ["Ripgrep App"],
        "desc": "Duplicate token should be ignored",
        "version": "1.0",
        "analytics": {"install": {"30d": {"ripgrep": 100000}}},
    }
]


def test_homebrew_formulae_adapter_properties() -> None:
    adapter = HomebrewFormulaeAdapter()

    assert adapter.name == "homebrew_formulae"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.formulae_url == HOMEBREW_FORMULAE_URL
    assert adapter.casks_url == HOMEBREW_CASKS_URL
    assert adapter.include_casks is True
    assert adapter.queries == []
    assert adapter.categories == []
    assert adapter.min_install_count == 0


def test_homebrew_formulae_adapter_custom_config() -> None:
    adapter = HomebrewFormulaeAdapter(
        config={
            "formulae_url": "https://example.test/formula.json",
            "casks_url": "https://example.test/cask.json",
            "include_casks": False,
            "queries": ["python"],
            "categories": ["homebrew/core"],
            "watchlist_terms": ["automation"],
            "min_install_count": 100,
        }
    )

    assert adapter.formulae_url == "https://example.test/formula.json"
    assert adapter.casks_url == "https://example.test/cask.json"
    assert adapter.include_casks is False
    assert adapter.queries == ["python", "automation"]
    assert adapter.categories == ["homebrew/core", "automation"]
    assert adapter.min_install_count == 100


@pytest.mark.asyncio
async def test_homebrew_formulae_fetches_formula_only() -> None:
    adapter = HomebrewFormulaeAdapter(config={"include_casks": False})

    with patch("max.sources.homebrew_formulae.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_FORMULAE)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 2
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.args[0] == HOMEBREW_FORMULAE_URL

    first = signals[0]
    assert first.id == "homebrew_formulae:formula:ripgrep"
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "homebrew_formulae"
    assert first.title == "ripgrep@14.1.1"
    assert first.content == "Search tool like grep and The Silver Searcher"
    assert first.url == "https://formulae.brew.sh/formula/ripgrep"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.tags == ["formula", "homebrew/core", "pcre2", "rust"]
    assert first.credibility > 0.6
    assert first.metadata["name"] == "ripgrep"
    assert first.metadata["token"] == "ripgrep"
    assert first.metadata["tap"] == "homebrew/core"
    assert first.metadata["homepage"] == "https://github.com/BurntSushi/ripgrep"
    assert first.metadata["versions"] == {"stable": "14.1.1", "head": "HEAD"}
    assert first.metadata["analytics"] == MOCK_FORMULAE[0]["analytics"]
    assert first.metadata["artifact_type"] == "formula"
    assert first.metadata["source_url"] == HOMEBREW_FORMULAE_URL
    assert first.metadata["install_count"] == 22000


@pytest.mark.asyncio
async def test_homebrew_formulae_includes_casks() -> None:
    adapter = HomebrewFormulaeAdapter()

    with patch("max.sources.homebrew_formulae.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: [MOCK_FORMULAE[0]]),
            MagicMock(json=lambda: MOCK_CASKS),
        ]

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 2
    cask = signals[1]
    assert cask.id == "homebrew_formulae:cask:visual-studio-code"
    assert cask.title == "visual-studio-code"
    assert cask.url == "https://formulae.brew.sh/cask/visual-studio-code"
    assert cask.tags == ["cask", "homebrew/cask", "app", "binary", ">= :monterey"]
    assert cask.metadata["name"] == "Visual Studio Code"
    assert cask.metadata["token"] == "visual-studio-code"
    assert cask.metadata["versions"] == {"version": "1.100.0"}
    assert cask.metadata["artifact_type"] == "cask"
    assert cask.metadata["source_url"] == HOMEBREW_CASKS_URL


@pytest.mark.asyncio
async def test_homebrew_formulae_filters_queries_categories_and_min_installs() -> None:
    adapter = HomebrewFormulaeAdapter(
        config={
            "include_casks": False,
            "queries": ["python"],
            "categories": ["homebrew/core"],
            "min_install_count": 20_000,
        }
    )

    with patch("max.sources.homebrew_formulae.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_FORMULAE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 0

    adapter = HomebrewFormulaeAdapter(
        config={
            "include_casks": False,
            "queries": ["python"],
            "categories": ["homebrew/core"],
            "min_install_count": 10_000,
        }
    )
    with patch("max.sources.homebrew_formulae.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_FORMULAE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["token"] == "uv"


@pytest.mark.asyncio
async def test_homebrew_formulae_deduplicates_by_token_across_formulae_and_casks() -> None:
    adapter = HomebrewFormulaeAdapter()

    with patch("max.sources.homebrew_formulae.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: [MOCK_FORMULAE[0]]),
            MagicMock(json=lambda: MOCK_DUPLICATE_CASKS),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["artifact_type"] == "formula"
    assert signals[0].metadata["token"] == "ripgrep"


@pytest.mark.asyncio
async def test_homebrew_formulae_handles_missing_optional_fields() -> None:
    adapter = HomebrewFormulaeAdapter(config={"include_casks": False})
    payload = [{"name": "minimal"}]

    with patch("max.sources.homebrew_formulae.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: payload)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "minimal"
    assert signal.content == "minimal"
    assert signal.published_at is None
    assert signal.tags == ["formula"]
    assert signal.credibility == 0.1
    assert signal.metadata["homepage"] is None
    assert signal.metadata["versions"] == {}
    assert signal.metadata["analytics"] == {}


@pytest.mark.asyncio
async def test_homebrew_formulae_handles_http_and_malformed_payloads() -> None:
    adapter = HomebrewFormulaeAdapter()

    with patch("max.sources.homebrew_formulae.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            AdapterFetchError("homebrew_formulae", 500, HOMEBREW_FORMULAE_URL),
            MagicMock(json=lambda: {"not": "a list"}),
        ]

        signals = await adapter.fetch(limit=10)

    assert signals == []
