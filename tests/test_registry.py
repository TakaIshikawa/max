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
    get_adapter_metadata,
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


def test_get_adapter_metadata_reports_config_keys_required_keys_and_descriptions():
    with patch(
        "max.config.MAX_ADAPTERS",
        "hackernews,rss_feed,crates_io,dockerhub,mcp_registry,stackshare,bluesky,mastodon,huggingface,awesome_lists,github_pull_requests,gitlab_merge_requests,stackoverflow_survey",
    ), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        metadata = get_adapter_metadata()

    assert set(metadata) == {
        "hackernews",
        "rss_feed",
        "crates_io",
        "dockerhub",
        "mcp_registry",
        "stackshare",
        "bluesky",
        "mastodon",
        "huggingface",
        "awesome_lists",
        "github_pull_requests",
        "gitlab_merge_requests",
        "stackoverflow_survey",
    }
    assert metadata["hackernews"].config_keys == ["filter_keywords"]
    assert metadata["hackernews"].required_keys == []
    assert "Hacker News" in metadata["hackernews"].description
    assert metadata["rss_feed"].config_keys == ["feeds", "tags", "max_age_days"]
    assert metadata["rss_feed"].required_keys == ["feeds"]
    assert "RSS" in metadata["rss_feed"].description
    assert metadata["crates_io"].config_keys == ["queries", "categories"]
    assert metadata["crates_io"].required_keys == []
    assert "Crates.io" in metadata["crates_io"].description
    assert metadata["dockerhub"].config_keys == ["repositories", "queries", "include_tags"]
    assert metadata["dockerhub"].required_keys == []
    assert "Docker Hub" in metadata["dockerhub"].description
    assert metadata["mcp_registry"].config_keys == [
        "base_url",
        "endpoint",
        "queries",
        "categories",
        "min_stars",
        "min_score",
    ]
    assert metadata["mcp_registry"].required_keys == []
    assert "MCP server registry" in metadata["mcp_registry"].description
    assert metadata["stackshare"].config_keys == ["stacks", "categories", "base_url"]
    assert metadata["stackshare"].required_keys == []
    assert "StackShare" in metadata["stackshare"].description
    assert metadata["bluesky"].config_keys == ["queries", "domains"]
    assert metadata["bluesky"].required_keys == []
    assert "Bluesky" in metadata["bluesky"].description
    assert metadata["mastodon"].config_keys == [
        "instances",
        "hashtags",
        "accounts",
        "exclude_reblogs",
        "min_favourites",
        "max_age_days",
        "access_token_env",
    ]
    assert metadata["mastodon"].required_keys == []
    assert "Mastodon" in metadata["mastodon"].description
    assert metadata["huggingface"].config_keys == [
        "queries",
        "resource_types",
        "sort",
        "limit_per_query",
    ]
    assert metadata["huggingface"].required_keys == []
    assert "Hugging Face Hub" in metadata["huggingface"].description
    assert metadata["awesome_lists"].config_keys == [
        "lists",
        "topics",
        "include_descriptions",
        "github_token",
    ]
    assert metadata["awesome_lists"].required_keys == []
    assert "awesome-list" in metadata["awesome_lists"].description
    assert metadata["github_pull_requests"].config_keys == [
        "queries",
        "repositories",
        "labels",
        "state",
        "min_comments",
        "max_age_days",
        "github_token",
        "token",
        "token_env",
    ]
    assert metadata["github_pull_requests"].required_keys == []
    assert "pull request" in metadata["github_pull_requests"].description
    assert metadata["gitlab_merge_requests"].config_keys == [
        "project_ids",
        "queries",
        "labels",
        "state",
        "min_upvotes",
        "max_age_days",
        "gitlab_base_url",
        "token_env",
    ]
    assert metadata["gitlab_merge_requests"].required_keys == []
    assert "merge request" in metadata["gitlab_merge_requests"].description
    assert metadata["stackoverflow_survey"].config_keys == [
        "survey_urls",
        "local_paths",
        "question_filters",
        "min_percent",
        "max_rows",
    ]
    assert metadata["stackoverflow_survey"].required_keys == []
    assert "survey CSV" in metadata["stackoverflow_survey"].description


def test_get_adapter_returns_instance():
    adapter = get_adapter("hackernews")
    assert isinstance(adapter, SourceAdapter)
    assert adapter.name == "hackernews"


def test_get_adapter_raises_for_unknown():
    with pytest.raises(KeyError, match="Unknown adapter"):
        get_adapter("does_not_exist")


# ── Entry point non-SourceAdapter handling ───────────────────────────


def test_entry_point_warns_if_not_source_adapter_subclass(caplog):
    """Entry point loading a non-SourceAdapter class logs a warning and skips it."""
    class NotAnAdapter:
        pass

    class FakeEntryPoint:
        name = "invalid_adapter"
        def load(self):
            return NotAnAdapter

    with patch(
        "max.sources.registry.importlib.metadata.entry_points",
        return_value=[FakeEntryPoint()],
    ):
        discovered = _discover_adapters()

    assert "invalid_adapter" not in discovered
    assert "not a SourceAdapter subclass" in caplog.text


def test_entry_point_warns_on_load_failure(caplog):
    """Entry point that raises during load() logs a warning and skips it."""
    class FailingEntryPoint:
        name = "broken_adapter"
        def load(self):
            raise RuntimeError("Failed to load")

    with patch(
        "max.sources.registry.importlib.metadata.entry_points",
        return_value=[FailingEntryPoint()],
    ):
        discovered = _discover_adapters()

    assert "broken_adapter" not in discovered
    assert "Failed to load adapter entry_point" in caplog.text


# ── get_all_adapters with source_configs ──────────────────────────────


def test_get_all_adapters_with_source_configs_as_dicts():
    """get_all_adapters accepts list of dicts with adapter, enabled, params."""
    from max.sources.hackernews import HackerNewsAdapter

    # Mock registry to have only hackernews and reddit
    with patch("max.config.MAX_ADAPTERS", "hackernews,reddit"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        source_configs = [
            {"adapter": "hackernews", "enabled": True, "params": {"limit": 50}},
            {"adapter": "reddit", "enabled": True, "params": {}},
        ]
        adapters = get_all_adapters(source_configs=source_configs)

    assert len(adapters) == 2
    assert all(isinstance(a, SourceAdapter) for a in adapters)

    # Verify hackernews adapter received custom params
    hn_adapter = next(a for a in adapters if a.name == "hackernews")
    assert isinstance(hn_adapter, HackerNewsAdapter)
    assert hn_adapter._config == {"limit": 50}


def test_get_all_adapters_with_source_config_objects():
    """get_all_adapters accepts list of SourceConfig Pydantic objects."""
    from max.profiles.schema import SourceConfig

    with patch("max.config.MAX_ADAPTERS", "hackernews,reddit"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        source_configs = [
            SourceConfig(adapter="hackernews", enabled=True, params={"limit": 100}),
            SourceConfig(adapter="reddit", enabled=True, params={"subreddits": ["python"]}),
        ]
        adapters = get_all_adapters(source_configs=source_configs)

    assert len(adapters) == 2
    names = {a.name for a in adapters}
    assert names == {"hackernews", "reddit"}


def test_get_all_adapters_skips_disabled_adapters():
    """When enabled=False, adapter is not instantiated."""
    with patch("max.config.MAX_ADAPTERS", "hackernews,reddit"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        source_configs = [
            {"adapter": "hackernews", "enabled": True, "params": {}},
            {"adapter": "reddit", "enabled": False, "params": {}},
        ]
        adapters = get_all_adapters(source_configs=source_configs)

    assert len(adapters) == 1
    assert adapters[0].name == "hackernews"


def test_get_all_adapters_warns_for_unknown_adapter(caplog):
    """Unknown adapter name in source_configs logs a warning and is skipped."""
    with patch("max.config.MAX_ADAPTERS", "hackernews"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        source_configs = [
            {"adapter": "hackernews", "enabled": True, "params": {}},
            {"adapter": "nonexistent_adapter", "enabled": True, "params": {}},
        ]
        adapters = get_all_adapters(source_configs=source_configs)

    assert len(adapters) == 1
    assert adapters[0].name == "hackernews"
    assert "Profile references unknown adapter: nonexistent_adapter" in caplog.text


def test_get_all_adapters_passes_custom_params_to_constructor():
    """Custom params in source_configs are passed to adapter constructor."""
    with patch("max.config.MAX_ADAPTERS", "hackernews"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()

        custom_params = {"filter_keywords": ["mcp", "ai"], "limit": 75}
        source_configs = [
            {"adapter": "hackernews", "enabled": True, "params": custom_params},
        ]
        adapters = get_all_adapters(source_configs=source_configs)

    assert len(adapters) == 1
    assert adapters[0]._config == custom_params


def test_get_all_adapters_without_config_uses_defaults():
    """When source_configs=None, all adapters are instantiated with default config."""
    with patch("max.config.MAX_ADAPTERS", "hackernews,reddit"), \
         patch("max.config.MAX_ADAPTERS_EXCLUDE", ""):
        reload_registry()
        adapters = get_all_adapters(source_configs=None)

    assert len(adapters) == 2
    for adapter in adapters:
        # Default config is empty dict
        assert adapter._config == {}
