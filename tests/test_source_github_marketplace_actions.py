"""Tests for the GitHub Marketplace Actions source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.github_marketplace_actions import (
    GITHUB_API_SEARCH_REPOSITORIES,
    GitHubMarketplaceActionsAdapter,
    _DEFAULT_QUERIES,
)
from max.types.signal import SignalSourceType


SEARCH_RESPONSE = {
    "items": [
        {
            "id": 101,
            "full_name": "actions/setup-python",
            "name": "setup-python",
            "description": "Set up Python in GitHub Actions.",
            "html_url": "https://github.com/actions/setup-python",
            "owner": {"login": "actions"},
            "stargazers_count": 5100,
            "forks_count": 1800,
            "watchers_count": 5100,
            "open_issues_count": 45,
            "topics": ["github-action", "python", "setup"],
            "language": "TypeScript",
            "license": {"spdx_id": "MIT"},
            "created_at": "2019-09-03T12:00:00Z",
            "updated_at": "2026-04-20T11:30:00Z",
            "category": "continuous-integration",
            "install_count": 2500000,
        },
        {
            "id": 202,
            "repository": {
                "full_name": "docker/login-action",
                "name": "login-action",
                "description": "Log in to a Docker registry.",
                "html_url": "https://github.com/docker/login-action",
                "owner": {"login": "docker"},
                "stargazers_count": 3800,
                "topics": ["github-action", "docker", "deployment"],
                "created_at": "2020-01-01T00:00:00Z",
                "updated_at": "2026-04-19T10:00:00Z",
            },
            "marketplace_name": "Docker Login",
            "primary_category": "deployment",
            "usage_count": 900000,
        },
    ]
}


def test_github_marketplace_actions_adapter_properties() -> None:
    adapter = GitHubMarketplaceActionsAdapter()

    assert adapter.name == "github_marketplace_actions"
    assert adapter.source_type == SignalSourceType.MARKETPLACE.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.categories == []
    assert adapter.max_results is None
    assert adapter.min_stars == 0
    assert adapter.max_age_days is None
    assert adapter.token is None


def test_github_marketplace_actions_custom_config_and_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_TEST_GITHUB_TOKEN", "env-token")
    adapter = GitHubMarketplaceActionsAdapter(
        config={
            "queries": ["agent"],
            "watchlist_terms": ["mcp"],
            "categories": ["Deployment"],
            "max_results": "5",
            "min_stars": "100",
            "max_age_days": "30",
            "token_env": "MAX_TEST_GITHUB_TOKEN",
        }
    )

    assert adapter.queries == ["agent", "mcp"]
    assert adapter.categories == ["Deployment"]
    assert adapter.max_results == 5
    assert adapter.min_stars == 100
    assert adapter.max_age_days == 30
    assert adapter.token == "env-token"


@pytest.mark.asyncio
async def test_github_marketplace_actions_fetch_emits_signals_from_search_results() -> None:
    adapter = GitHubMarketplaceActionsAdapter(config={"queries": ["python"], "max_results": 10})

    with patch("max.sources.github_marketplace_actions.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: SEARCH_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == GITHUB_API_SEARCH_REPOSITORIES
    assert mock_fetch.call_args.kwargs["params"]["q"] == "topic:github-action python"
    assert mock_fetch.call_args.kwargs["params"]["sort"] == "stars"
    assert mock_fetch.call_args.kwargs["headers"]["Accept"] == "application/vnd.github+json"

    first = signals[0]
    assert first.id == "github_marketplace_actions:actions/setup-python"
    assert first.source_type == SignalSourceType.MARKETPLACE
    assert first.source_adapter == "github_marketplace_actions"
    assert first.title == "actions/setup-python"
    assert first.content == (
        "Set up Python in GitHub Actions. (2,500,000 installs; 5,100 stars; "
        "category: continuous-integration; publisher: actions)"
    )
    assert first.url == "https://github.com/actions/setup-python"
    assert first.author == "actions"
    assert first.published_at == datetime(2019, 9, 3, 12, tzinfo=timezone.utc)
    assert first.tags == ["continuous-integration", "github-action", "python", "setup"]
    assert first.credibility > 0.8
    assert first.metadata["repository"] == "actions/setup-python"
    assert first.metadata["publisher"] == "actions"
    assert first.metadata["install_count"] == 2500000
    assert first.metadata["stars"] == 5100
    assert first.metadata["category"] == "continuous-integration"
    assert first.metadata["topics"] == ["github-action", "python", "setup"]
    assert first.metadata["language"] == "TypeScript"
    assert first.metadata["license"] == "MIT"
    assert first.metadata["published_at"] == "2019-09-03T12:00:00+00:00"
    assert first.metadata["updated_at"] == "2026-04-20T11:30:00+00:00"
    assert first.metadata["source_url"] == first.url
    assert first.metadata["search_query"] == "python"

    assert signals[1].title == "docker/Docker Login"
    assert signals[1].metadata["install_count"] == 900000
    assert signals[1].metadata["category"] == "deployment"


@pytest.mark.asyncio
async def test_github_marketplace_actions_filters_and_deduplicates_results() -> None:
    adapter = GitHubMarketplaceActionsAdapter(
        config={
            "queries": ["python"],
            "categories": ["continuous integration"],
            "min_stars": 5000,
            "max_results": 1,
        }
    )
    response = {
        "items": [
            SEARCH_RESPONSE["items"][0],
            SEARCH_RESPONSE["items"][0],
            {
                **SEARCH_RESPONSE["items"][1]["repository"],
                "category": "deployment",
                "stargazers_count": 100,
            },
        ]
    }

    with patch("max.sources.github_marketplace_actions.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: response)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["repository"] == "actions/setup-python"
    assert mock_fetch.call_args.kwargs["params"]["q"] == (
        "topic:github-action python stars:>=5000"
    )
    assert mock_fetch.call_args.kwargs["params"]["per_page"] == 1


@pytest.mark.asyncio
async def test_github_marketplace_actions_category_search_affects_query() -> None:
    adapter = GitHubMarketplaceActionsAdapter(config={"queries": [], "categories": ["Code Quality"]})

    with patch("max.sources.github_marketplace_actions.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"items": []})

        signals = await adapter.fetch(limit=5)

    assert signals == []
    assert mock_fetch.call_args.kwargs["params"]["q"] == "topic:github-action topic:code-quality"


@pytest.mark.asyncio
async def test_github_marketplace_actions_auth_header_uses_configured_token() -> None:
    adapter = GitHubMarketplaceActionsAdapter(config={"queries": ["agent"], "github_token": "secret"})

    with patch("max.sources.github_marketplace_actions.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"items": []})

        await adapter.fetch(limit=1)

    assert mock_fetch.call_args.kwargs["headers"]["Authorization"] == "Bearer secret"


@pytest.mark.asyncio
async def test_github_marketplace_actions_handles_malformed_and_empty_responses() -> None:
    adapter = GitHubMarketplaceActionsAdapter(config={"queries": ["agent"]})

    with patch("max.sources.github_marketplace_actions.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"unexpected": []})

        assert await adapter.fetch(limit=5) == []

    with patch("max.sources.github_marketplace_actions.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: "bad")

        assert await adapter.fetch(limit=5) == []


@pytest.mark.asyncio
async def test_github_marketplace_actions_handles_fetch_and_json_errors() -> None:
    adapter = GitHubMarketplaceActionsAdapter(config={"queries": ["agent"]})

    with patch("max.sources.github_marketplace_actions.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError(
            "github_marketplace_actions",
            500,
            GITHUB_API_SEARCH_REPOSITORIES,
        )

        assert await adapter.fetch(limit=5) == []

    with patch("max.sources.github_marketplace_actions.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=MagicMock(side_effect=ValueError("bad json")))

        assert await adapter.fetch(limit=5) == []
