"""Tests for adapter parameterization via config dicts."""

from __future__ import annotations

from max.profiles.schema import SourceConfig
from max.sources.arxiv import ArxivAdapter
from max.sources.devto import DevtoAdapter
from max.sources.github import GitHubAdapter, _DEFAULT_TOPICS
from max.sources.github_issues import GitHubIssuesAdapter, _DEFAULT_QUERIES as GH_DEFAULT_QUERIES
from max.sources.hackernews import HackerNewsAdapter
from max.sources.nvd_cve import NvdCveAdapter
from max.sources.npm_registry import NpmRegistryAdapter, _DEFAULT_QUERIES as NPM_DEFAULT_QUERIES
from max.sources.product_hunt import ProductHuntAdapter, _DEFAULT_TOPICS as PH_DEFAULT_TOPICS
from max.sources.pubmed import PubMedAdapter
from max.sources.pypi_registry import PyPIRegistryAdapter, _DEFAULT_KEYWORDS
from max.sources.reddit import RedditAdapter, _DEFAULT_SUBREDDITS
from max.sources.registry import get_all_adapters, reload_registry
from max.sources.security_advisories import (
    SecurityAdvisoriesAdapter,
    _DEFAULT_ECOSYSTEMS,
    _DEFAULT_SEVERITIES,
)


# --- Default config (backward compat) ---


def test_reddit_default_config():
    adapter = RedditAdapter()
    assert adapter.subreddits == _DEFAULT_SUBREDDITS


def test_github_default_config():
    adapter = GitHubAdapter()
    assert adapter.topics == _DEFAULT_TOPICS


def test_github_issues_default_config():
    adapter = GitHubIssuesAdapter()
    assert adapter.queries == GH_DEFAULT_QUERIES


def test_npm_default_config():
    adapter = NpmRegistryAdapter()
    assert adapter.queries == NPM_DEFAULT_QUERIES


def test_pypi_default_config():
    adapter = PyPIRegistryAdapter()
    assert adapter.keywords == _DEFAULT_KEYWORDS


def test_security_advisories_default_config():
    adapter = SecurityAdvisoriesAdapter()
    assert adapter.ecosystems == _DEFAULT_ECOSYSTEMS
    assert adapter.severities == _DEFAULT_SEVERITIES


def test_product_hunt_default_config():
    adapter = ProductHuntAdapter()
    assert adapter.topics == PH_DEFAULT_TOPICS


def test_hackernews_default_config():
    adapter = HackerNewsAdapter()
    assert adapter.filter_keywords == []


# --- Custom config ---


def test_reddit_custom_subreddits():
    adapter = RedditAdapter(config={"subreddits": ["healthIT", "medicine"]})
    assert adapter.subreddits == ["healthIT", "medicine"]


def test_github_custom_topics():
    adapter = GitHubAdapter(config={"topics": ["healthcare", "fhir"]})
    assert adapter.topics == ["healthcare", "fhir"]


def test_github_issues_custom_queries():
    queries = ['"fhir" label:bug is:open']
    adapter = GitHubIssuesAdapter(config={"queries": queries})
    assert adapter.queries == queries


def test_npm_custom_queries():
    adapter = NpmRegistryAdapter(config={"queries": ["fhir", "hl7"]})
    assert adapter.queries == ["fhir", "hl7"]


def test_pypi_custom_keywords():
    adapter = PyPIRegistryAdapter(config={"keywords": ["fhir", "medical"]})
    assert adapter.keywords == {"fhir", "medical"}


def test_security_advisories_custom():
    adapter = SecurityAdvisoriesAdapter(
        config={"ecosystems": ["pip"], "severities": ["critical"]}
    )
    assert adapter.ecosystems == ["pip"]
    assert adapter.severities == ["critical"]


def test_product_hunt_custom_topics():
    adapter = ProductHuntAdapter(config={"topics": ["health-fitness"]})
    assert adapter.topics == ["health-fitness"]


def test_hackernews_custom_filter():
    adapter = HackerNewsAdapter(config={"filter_keywords": ["health", "medical"]})
    assert adapter.filter_keywords == ["health", "medical"]


def test_query_adapters_include_normalized_watchlist_terms():
    watchlist_config = {"watchlist_terms": ["fhir", "prior auth"]}

    assert GitHubIssuesAdapter(config=watchlist_config).queries == [
        *GH_DEFAULT_QUERIES,
        "fhir",
        "prior auth",
    ]
    assert NpmRegistryAdapter(config=watchlist_config).queries == [
        *NPM_DEFAULT_QUERIES,
        "fhir",
        "prior auth",
    ]
    assert "fhir" in ArxivAdapter(config=watchlist_config).queries
    assert "prior auth" in PubMedAdapter(config=watchlist_config).queries


def test_category_filter_adapters_include_normalized_watchlist_terms():
    watchlist_config = {"watchlist_terms": ["fhir", "clinical"]}

    assert GitHubAdapter(config=watchlist_config).topics == [
        *_DEFAULT_TOPICS,
        "fhir",
        "clinical",
    ]
    assert ProductHuntAdapter(config=watchlist_config).topics == [
        *PH_DEFAULT_TOPICS,
        "fhir",
        "clinical",
    ]
    assert HackerNewsAdapter(config=watchlist_config).filter_keywords == ["fhir", "clinical"]
    assert DevtoAdapter(config=watchlist_config).tags[-2:] == ["fhir", "clinical"]
    assert NvdCveAdapter(config=watchlist_config).keywords == ["fhir", "clinical"]


# --- Registry with source configs ---


def test_registry_with_source_configs():
    """get_all_adapters with source_configs returns only configured adapters."""
    reload_registry()
    configs = [
        SourceConfig(adapter="reddit", params={"subreddits": ["test"]}),
        SourceConfig(adapter="hackernews"),
    ]
    adapters = get_all_adapters(source_configs=configs)
    assert len(adapters) == 2
    names = {a.name for a in adapters}
    assert names == {"reddit", "hackernews"}

    # Verify config was passed through
    reddit = next(a for a in adapters if a.name == "reddit")
    assert reddit.subreddits == ["test"]


def test_registry_passes_normalized_watchlist_config():
    reload_registry()
    configs = [
        SourceConfig(
            adapter="npm_registry",
            watchlist=["fhir", "ehr"],
            params={"queries": ["hl7"]},
        ),
    ]
    adapters = get_all_adapters(source_configs=configs)

    assert len(adapters) == 1
    assert adapters[0].queries == ["hl7", "fhir", "ehr"]


def test_registry_disabled_adapter_skipped():
    reload_registry()
    configs = [
        SourceConfig(adapter="reddit", enabled=True),
        SourceConfig(adapter="hackernews", enabled=False),
    ]
    adapters = get_all_adapters(source_configs=configs)
    assert len(adapters) == 1
    assert adapters[0].name == "reddit"


def test_registry_unknown_adapter_skipped():
    reload_registry()
    configs = [
        SourceConfig(adapter="nonexistent_adapter"),
        SourceConfig(adapter="hackernews"),
    ]
    adapters = get_all_adapters(source_configs=configs)
    assert len(adapters) == 1
    assert adapters[0].name == "hackernews"


def test_registry_no_configs_returns_all():
    """get_all_adapters(None) returns all discovered adapters (backward compat)."""
    reload_registry()
    adapters = get_all_adapters(source_configs=None)
    assert len(adapters) >= 7  # At least the built-in adapters
