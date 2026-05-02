"""Tests for dynamic adapter plugin loading."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class FakeAdapter(SourceAdapter):
    """Test adapter for plugin loading tests."""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return []


class AnotherFakeAdapter(SourceAdapter):
    """Another test adapter."""

    @property
    def name(self) -> str:
        return "another_fake"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return []


@pytest.fixture(autouse=True)
def _clear_registry():
    """Reset the registry cache before each test."""
    from max.sources.registry import reload_registry

    reload_registry()
    yield
    reload_registry()


def _make_entry_point(name: str, cls: type) -> MagicMock:
    """Create a mock entry_point."""
    ep = MagicMock()
    ep.name = name
    ep.load.return_value = cls
    return ep


def test_discover_via_entry_points():
    """Adapters are discovered via entry_points when available."""
    from max.sources.registry import _discover_adapters

    eps = [
        _make_entry_point("fake", FakeAdapter),
        _make_entry_point("another", AnotherFakeAdapter),
    ]

    with patch("max.sources.registry.importlib.metadata.entry_points", return_value=eps):
        adapters = _discover_adapters()

    assert "fake" in adapters
    assert "another" in adapters
    assert adapters["fake"] is FakeAdapter


def test_fallback_to_builtins():
    """When entry_points returns nothing, built-in adapters are loaded."""
    from max.sources.registry import _discover_adapters

    with patch("max.sources.registry.importlib.metadata.entry_points", return_value=[]):
        adapters = _discover_adapters()

    # Should have the 8 built-in adapters
    assert "hackernews" in adapters
    assert "reddit" in adapters
    assert "github" in adapters
    assert "npm_registry" in adapters
    assert "pypi_registry" in adapters
    assert "github_issues" in adapters
    assert "github_actions" in adapters
    assert "security_advisories" in adapters
    assert "product_hunt" in adapters
    assert "crates_io" in adapters


def test_entry_point_load_failure_skipped():
    """A failing entry_point is skipped, others still load."""
    from max.sources.registry import _discover_adapters

    bad_ep = MagicMock()
    bad_ep.name = "broken"
    bad_ep.load.side_effect = ImportError("missing dependency")

    good_ep = _make_entry_point("fake", FakeAdapter)

    with patch(
        "max.sources.registry.importlib.metadata.entry_points",
        return_value=[bad_ep, good_ep],
    ):
        adapters = _discover_adapters()

    assert "fake" in adapters
    assert "broken" not in adapters


def test_include_filter():
    """MAX_ADAPTERS restricts to named adapters only."""
    from max.sources.registry import _filter_adapters

    adapters = {"hackernews": FakeAdapter, "reddit": AnotherFakeAdapter, "github": FakeAdapter}

    with patch("max.config.MAX_ADAPTERS", "hackernews,reddit"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        filtered = _filter_adapters(adapters)

    assert set(filtered.keys()) == {"hackernews", "reddit"}


def test_exclude_filter():
    """MAX_ADAPTERS_EXCLUDE removes named adapters."""
    from max.sources.registry import _filter_adapters

    adapters = {"hackernews": FakeAdapter, "reddit": AnotherFakeAdapter, "github": FakeAdapter}

    with patch("max.config.MAX_ADAPTERS", "all"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", "reddit"):
        filtered = _filter_adapters(adapters)

    assert "reddit" not in filtered
    assert "hackernews" in filtered
    assert "github" in filtered


def test_all_adapters_no_filter():
    """MAX_ADAPTERS=all with no excludes returns everything."""
    from max.sources.registry import _filter_adapters

    adapters = {"hackernews": FakeAdapter, "reddit": AnotherFakeAdapter}

    with patch("max.config.MAX_ADAPTERS", "all"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        filtered = _filter_adapters(adapters)

    assert set(filtered.keys()) == {"hackernews", "reddit"}


def test_get_all_adapters_returns_instances():
    """get_all_adapters returns instantiated adapter objects."""
    from max.sources.registry import get_all_adapters

    adapters = get_all_adapters()
    assert len(adapters) > 0
    for adapter in adapters:
        assert isinstance(adapter, SourceAdapter)
        assert adapter.name  # Has a name


def test_list_adapters_returns_names():
    """list_adapters returns adapter name strings."""
    from max.sources.registry import list_adapters

    names = list_adapters()
    assert isinstance(names, list)
    assert len(names) > 0
    assert all(isinstance(n, str) for n in names)


def test_get_adapter_by_name():
    """get_adapter returns a specific adapter."""
    from max.sources.registry import get_adapter, list_adapters

    names = list_adapters()
    if names:
        adapter = get_adapter(names[0])
        assert isinstance(adapter, SourceAdapter)


def test_get_adapter_unknown_raises():
    """get_adapter raises KeyError for unknown name."""
    from max.sources.registry import get_adapter

    with pytest.raises(KeyError, match="Unknown adapter"):
        get_adapter("nonexistent_adapter")


def test_reload_clears_cache():
    """reload_registry clears the cache so next call re-discovers."""
    from max.sources import registry

    # Force cache population
    registry.get_all_adapters()
    assert registry._cache is not None

    registry.reload_registry()
    assert registry._cache is None


def test_github_actions_metadata_and_registry_loading():
    """GitHub Actions adapter is exposed through the registry with metadata."""
    from max.sources.github_actions import GitHubActionsAdapter
    from max.sources.registry import get_adapter, get_adapter_metadata

    adapter = get_adapter("github_actions")
    metadata = get_adapter_metadata()["github_actions"]

    assert isinstance(adapter, GitHubActionsAdapter)
    assert metadata.name == "github_actions"
    assert "repositories" in metadata.config_keys
    assert "workflow_names" in metadata.config_keys
    assert "conclusions" in metadata.config_keys
    assert "max_age_days" in metadata.config_keys


def test_github_repository_topics_metadata_and_registry_loading():
    """GitHub repository topics adapter is exposed through the registry with metadata."""
    from max.sources.github_repository_topics import GitHubRepositoryTopicsAdapter
    from max.sources.registry import get_adapter, get_adapter_metadata

    adapter = get_adapter("github_repository_topics")
    metadata = get_adapter_metadata()["github_repository_topics"]

    assert isinstance(adapter, GitHubRepositoryTopicsAdapter)
    assert metadata.name == "github_repository_topics"
    assert "repositories" in metadata.config_keys
    assert "token" in metadata.config_keys
    assert "token_env" in metadata.config_keys


def test_openssf_scorecard_metadata_and_registry_loading():
    """OpenSSF Scorecard adapter is exposed through the registry with metadata."""
    from max.sources.openssf_scorecard import OpenSSFScorecardAdapter
    from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters

    adapter = get_adapter("openssf_scorecard")
    metadata = get_adapter_metadata()["openssf_scorecard"]

    assert "openssf_scorecard" in list_adapters()
    assert isinstance(adapter, OpenSSFScorecardAdapter)
    assert metadata.name == "openssf_scorecard"
    assert "repositories" in metadata.config_keys
    assert "min_risk_score" in metadata.config_keys
    assert "checks" in metadata.config_keys
    assert "token" in metadata.config_keys
    assert "token_env" in metadata.config_keys
    assert "local_path" in metadata.config_keys


def test_hexpm_download_trends_metadata_and_registry_loading():
    """Hex.pm download trends adapter is exposed through the registry."""
    from max.sources.hexpm_download_trends import HexPmDownloadTrendsAdapter
    from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters

    adapter = get_adapter("hexpm_download_trends")
    metadata = get_adapter_metadata()["hexpm_download_trends"]

    assert "hexpm_download_trends" in list_adapters()
    assert isinstance(adapter, HexPmDownloadTrendsAdapter)
    assert metadata.name == "hexpm_download_trends"
    assert "packages" in metadata.config_keys
    assert "period" in metadata.config_keys
    assert "api_base_url" in metadata.config_keys
