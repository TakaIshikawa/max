"""Tests for the source adapter registry discovery and filtering logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from max.sources.base import SourceAdapter
from max.sources.registry import (
    _BUILTIN_ADAPTERS,
    _discover_adapters,
    _filter_adapters,
    _get_registry,
    get_adapter,
    get_all_adapters,
    list_adapters,
    reload_registry,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    """Clear the registry cache before and after each test."""
    reload_registry()
    yield
    reload_registry()


# ── Discovery (get_all_adapters / list_adapters) ─────────────────────


def test_returns_all_builtin_adapters_when_env_unset():
    """When MAX_ADAPTERS defaults to 'all', all built-in adapters are returned."""
    with patch("max.config.MAX_ADAPTERS", "all"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        adapters = get_all_adapters()

    names = {a.name for a in adapters}
    for builtin_name in _BUILTIN_ADAPTERS:
        assert builtin_name in names, f"Missing built-in adapter: {builtin_name}"


def test_returns_all_builtin_adapters_when_set_to_all():
    """When MAX_ADAPTERS='all', all built-in adapters are returned."""
    with patch("max.config.MAX_ADAPTERS", "all"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        adapters = get_all_adapters()

    names = {a.name for a in adapters}
    for builtin_name in _BUILTIN_ADAPTERS:
        assert builtin_name in names


# ── Filtering by MAX_ADAPTERS ────────────────────────────────────────


def test_filters_to_named_adapters():
    """When MAX_ADAPTERS is a comma-separated list, only those adapters load."""
    with patch("max.config.MAX_ADAPTERS", "hackernews,reddit"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        adapters = get_all_adapters()

    names = {a.name for a in adapters}
    assert names == {"hackernews", "reddit"}


def test_filters_with_whitespace_in_list():
    """Whitespace around adapter names in MAX_ADAPTERS is stripped."""
    with patch("max.config.MAX_ADAPTERS", " hackernews , reddit "), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        adapters = get_all_adapters()

    names = {a.name for a in adapters}
    assert names == {"hackernews", "reddit"}


# ── Exclusion via MAX_ADAPTERS_EXCLUDE ───────────────────────────────


def test_excludes_named_adapters():
    """MAX_ADAPTERS_EXCLUDE removes listed adapters from the result."""
    with patch("max.config.MAX_ADAPTERS", "all"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", "hackernews,reddit"):
        adapters = get_all_adapters()

    names = {a.name for a in adapters}
    assert "hackernews" not in names
    assert "reddit" not in names
    assert len(names) == len(_BUILTIN_ADAPTERS) - 2


# ── Combined include + exclude ───────────────────────────────────────


def test_exclude_takes_precedence_over_include():
    """When both MAX_ADAPTERS and MAX_ADAPTERS_EXCLUDE are set, exclude wins."""
    with patch("max.config.MAX_ADAPTERS", "hackernews,reddit,github"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", "reddit"):
        adapters = get_all_adapters()

    names = {a.name for a in adapters}
    assert names == {"hackernews", "github"}


# ── Adapter instances are valid SourceAdapters ───────────────────────


def test_each_adapter_is_source_adapter_with_name_and_source_type():
    """Every returned adapter is a SourceAdapter with non-empty name and source_type."""
    with patch("max.config.MAX_ADAPTERS", "all"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        adapters = get_all_adapters()

    assert len(adapters) >= len(_BUILTIN_ADAPTERS)
    for adapter in adapters:
        assert isinstance(adapter, SourceAdapter)
        assert isinstance(adapter.name, str) and len(adapter.name) > 0
        assert isinstance(adapter.source_type, str) and len(adapter.source_type) > 0


# ── Caching ──────────────────────────────────────────────────────────


def test_registry_caches_results():
    """_get_registry() returns the same dict object on subsequent calls."""
    first = _get_registry()
    second = _get_registry()
    assert first is second


def test_reload_registry_clears_cache():
    """reload_registry() forces re-discovery on next access."""
    first = _get_registry()
    reload_registry()
    fresh = _get_registry()

    # Same content but a new dict object
    assert first is not fresh
    assert set(first) == set(fresh)


# ── Fallback import mapping ──────────────────────────────────────────


def test_fallback_when_entry_points_returns_empty():
    """When entry_points discovery yields nothing, _BUILTIN_ADAPTERS are loaded."""
    with patch("max.sources.registry.importlib.metadata.entry_points", return_value=[]):
        discovered = _discover_adapters()

    assert len(discovered) == len(_BUILTIN_ADAPTERS)
    for name in _BUILTIN_ADAPTERS:
        assert name in discovered
        assert issubclass(discovered[name], SourceAdapter)


def test_fallback_skips_broken_builtin():
    """If a built-in module fails to import, it is skipped gracefully."""
    real_import_module = __import__("importlib").import_module

    def selective_import(name):
        if name == "max.sources.hackernews":
            raise ImportError("boom")
        return real_import_module(name)

    with patch("max.sources.registry.importlib.metadata.entry_points", return_value=[]), \
         patch("max.sources.registry.importlib.import_module", side_effect=selective_import):
        discovered = _discover_adapters()

    assert "hackernews" not in discovered
    # Other adapters still loaded
    assert len(discovered) == len(_BUILTIN_ADAPTERS) - 1


def test_entry_points_used_when_available():
    """When entry_points returns valid adapters, fallback is NOT used."""
    from max.sources.hackernews import HackerNewsAdapter

    class FakeEntryPoint:
        name = "hackernews"
        def load(self):
            return HackerNewsAdapter

    with patch(
        "max.sources.registry.importlib.metadata.entry_points",
        return_value=[FakeEntryPoint()],
    ), patch("max.sources.registry.importlib.import_module") as mock_import:
        discovered = _discover_adapters()

    # Entry point was used, so import_module (fallback) was NOT called
    mock_import.assert_not_called()
    assert "hackernews" in discovered
    assert discovered["hackernews"] is HackerNewsAdapter


# ── _filter_adapters unit tests ──────────────────────────────────────


def test_filter_adapters_all_passes_through():
    """When MAX_ADAPTERS='all' and no exclusions, all adapters pass."""
    from max.sources.hackernews import HackerNewsAdapter
    from max.sources.reddit import RedditAdapter

    sample = {"hackernews": HackerNewsAdapter, "reddit": RedditAdapter}

    with patch("max.config.MAX_ADAPTERS", "all"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        result = _filter_adapters(sample)

    assert result == sample


def test_filter_adapters_include_and_exclude():
    """_filter_adapters applies both include and exclude correctly."""
    from max.sources.github import GitHubAdapter
    from max.sources.hackernews import HackerNewsAdapter
    from max.sources.reddit import RedditAdapter

    sample = {
        "hackernews": HackerNewsAdapter,
        "reddit": RedditAdapter,
        "github": GitHubAdapter,
        "npm_registry": type("Dummy", (SourceAdapter,), {
            "name": property(lambda self: "npm_registry"),
            "source_type": property(lambda self: "registry"),
            "fetch": lambda self, **kw: [],
        }),
    }

    with patch("max.config.MAX_ADAPTERS", "hackernews,reddit,github"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", "github"):
        result = _filter_adapters(sample)

    assert set(result) == {"hackernews", "reddit"}


# ── list_adapters / get_adapter convenience functions ────────────────


def test_list_adapters_returns_strings():
    names = list_adapters()
    assert isinstance(names, list)
    assert all(isinstance(n, str) for n in names)
    assert "hackernews" in names


def test_get_adapter_returns_instance():
    adapter = get_adapter("hackernews")
    assert isinstance(adapter, SourceAdapter)
    assert adapter.name == "hackernews"


def test_get_adapter_raises_for_unknown():
    with pytest.raises(KeyError, match="Unknown adapter"):
        get_adapter("does_not_exist")
