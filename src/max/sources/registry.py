"""Adapter registry — discover and instantiate source adapters."""

from __future__ import annotations

from max.sources.base import SourceAdapter
from max.sources.github import GitHubAdapter
from max.sources.hackernews import HackerNewsAdapter
from max.sources.npm_registry import NpmRegistryAdapter
from max.sources.reddit import RedditAdapter

_ADAPTERS: dict[str, type[SourceAdapter]] = {
    "hackernews": HackerNewsAdapter,
    "npm_registry": NpmRegistryAdapter,
    "reddit": RedditAdapter,
    "github": GitHubAdapter,
}


def get_adapter(name: str) -> SourceAdapter:
    cls = _ADAPTERS.get(name)
    if cls is None:
        raise KeyError(f"Unknown adapter: {name}. Available: {list(_ADAPTERS)}")
    return cls()


def list_adapters() -> list[str]:
    return list(_ADAPTERS)


def get_all_adapters() -> list[SourceAdapter]:
    return [cls() for cls in _ADAPTERS.values()]
