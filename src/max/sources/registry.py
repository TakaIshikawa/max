"""Adapter registry — discover and instantiate source adapters.

Adapters are discovered via entry_points (group: max.adapters) for installed
packages, with a fallback to built-in imports for dev mode.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from dataclasses import dataclass

from max.sources.base import SourceAdapter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdapterMetadata:
    """Human-readable adapter configuration metadata."""

    name: str
    config_keys: list[str]
    required_keys: list[str]
    description: str

    @property
    def supported_config_keys(self) -> list[str]:
        """Alias for callers that prefer the full metadata term."""
        return self.config_keys


# Fallback mapping for dev mode (when package is not pip-installed).
_BUILTIN_ADAPTERS: dict[str, str] = {
    "hackernews": "max.sources.hackernews:HackerNewsAdapter",
    "npm_registry": "max.sources.npm_registry:NpmRegistryAdapter",
    "reddit": "max.sources.reddit:RedditAdapter",
    "github": "max.sources.github:GitHubAdapter",
    "github_releases": "max.sources.github_releases:GitHubReleasesAdapter",
    "pypi_registry": "max.sources.pypi_registry:PyPIRegistryAdapter",
    "github_issues": "max.sources.github_issues:GitHubIssuesAdapter",
    "security_advisories": "max.sources.security_advisories:SecurityAdvisoriesAdapter",
    "nvd_cve": "max.sources.nvd_cve:NvdCveAdapter",
    "product_hunt": "max.sources.product_hunt:ProductHuntAdapter",
    "stackoverflow": "max.sources.stackoverflow:StackOverflowAdapter",
    "arxiv": "max.sources.arxiv:ArxivAdapter",
    "openalex": "max.sources.openalex:OpenAlexAdapter",
    "devto": "max.sources.devto:DevtoAdapter",
    "pubmed": "max.sources.pubmed:PubMedAdapter",
    "rss_feed": "max.sources.rss_feed:RssFeedAdapter",
    "crates_io": "max.sources.crates_io:CratesIoAdapter",
}

_BUILTIN_ADAPTER_METADATA: dict[str, AdapterMetadata] = {
    "hackernews": AdapterMetadata(
        name="hackernews",
        config_keys=["filter_keywords"],
        required_keys=[],
        description="Fetches Hacker News stories and optionally filters them by keywords.",
    ),
    "npm_registry": AdapterMetadata(
        name="npm_registry",
        config_keys=["queries"],
        required_keys=[],
        description="Searches the npm registry for packages matching configured query terms.",
    ),
    "reddit": AdapterMetadata(
        name="reddit",
        config_keys=["subreddits"],
        required_keys=[],
        description="Fetches posts from configured public subreddit names.",
    ),
    "github": AdapterMetadata(
        name="github",
        config_keys=["topics"],
        required_keys=[],
        description="Searches GitHub repositories for configured topics.",
    ),
    "github_releases": AdapterMetadata(
        name="github_releases",
        config_keys=[
            "repositories",
            "include_drafts",
            "include_prereleases",
            "github_token",
            "token",
        ],
        required_keys=[],
        description="Fetches release notes from configured GitHub repositories.",
    ),
    "pypi_registry": AdapterMetadata(
        name="pypi_registry",
        config_keys=["keywords"],
        required_keys=[],
        description="Fetches PyPI package signals matching configured keywords.",
    ),
    "github_issues": AdapterMetadata(
        name="github_issues",
        config_keys=["queries"],
        required_keys=[],
        description="Searches GitHub issues for configured query strings.",
    ),
    "security_advisories": AdapterMetadata(
        name="security_advisories",
        config_keys=["ecosystems", "severities"],
        required_keys=[],
        description="Fetches GitHub Security Advisory signals by ecosystem and severity.",
    ),
    "nvd_cve": AdapterMetadata(
        name="nvd_cve",
        config_keys=["keywords", "severities", "cvss_min", "max_age_days", "api_key_env"],
        required_keys=[],
        description="Fetches recent NVD CVE vulnerability signals matching configured filters.",
    ),
    "product_hunt": AdapterMetadata(
        name="product_hunt",
        config_keys=["topics"],
        required_keys=[],
        description="Fetches Product Hunt posts for configured topic slugs.",
    ),
    "stackoverflow": AdapterMetadata(
        name="stackoverflow",
        config_keys=["tags", "min_score", "unanswered_only"],
        required_keys=[],
        description="Fetches Stack Overflow questions for configured tags and score filters.",
    ),
    "arxiv": AdapterMetadata(
        name="arxiv",
        config_keys=["categories", "queries"],
        required_keys=[],
        description="Fetches arXiv papers matching configured categories and query expressions.",
    ),
    "openalex": AdapterMetadata(
        name="openalex",
        config_keys=[
            "search_terms",
            "concepts",
            "from_publication_date",
            "per_page",
            "mailto",
        ],
        required_keys=[],
        description="Fetches scholarly works from OpenAlex matching configured search and concept filters.",
    ),
    "devto": AdapterMetadata(
        name="devto",
        config_keys=["tags", "period"],
        required_keys=[],
        description="Fetches DEV Community articles for configured tags and time period.",
    ),
    "pubmed": AdapterMetadata(
        name="pubmed",
        config_keys=["queries", "max_results_per_query", "recent_days"],
        required_keys=[],
        description="Fetches PubMed article signals matching configured search queries.",
    ),
    "rss_feed": AdapterMetadata(
        name="rss_feed",
        config_keys=["feeds", "tags", "max_age_days"],
        required_keys=["feeds"],
        description="Fetches RSS or Atom entries from explicitly configured feed URLs.",
    ),
    "crates_io": AdapterMetadata(
        name="crates_io",
        config_keys=["queries", "categories"],
        required_keys=[],
        description="Searches Crates.io for Rust packages matching configured queries and categories.",
    ),
}


def _discover_adapters() -> dict[str, type[SourceAdapter]]:
    """Discover adapters via entry_points, falling back to built-in imports."""
    adapters: dict[str, type[SourceAdapter]] = {}

    # Try entry_points first
    try:
        eps = importlib.metadata.entry_points(group="max.adapters")
        for ep in eps:
            try:
                cls = ep.load()
                if isinstance(cls, type) and issubclass(cls, SourceAdapter):
                    adapters[ep.name] = cls
                else:
                    logger.warning("Entry point '%s' is not a SourceAdapter subclass", ep.name)
            except Exception:
                logger.warning("Failed to load adapter entry_point '%s'", ep.name, exc_info=True)
    except Exception:
        logger.debug("entry_points discovery unavailable", exc_info=True)

    # Fallback: if no entry_points found, load built-ins directly
    if not adapters:
        for name, target in _BUILTIN_ADAPTERS.items():
            module_path, cls_name = target.rsplit(":", 1)
            try:
                mod = importlib.import_module(module_path)
                cls = getattr(mod, cls_name)
                adapters[name] = cls
            except Exception:
                logger.warning("Failed to load built-in adapter '%s'", name, exc_info=True)

    return adapters


def _filter_adapters(
    adapters: dict[str, type[SourceAdapter]],
) -> dict[str, type[SourceAdapter]]:
    """Apply include/exclude config filters."""
    from max.config import MAX_ADAPTERS, MAX_ADAPTERS_EXCLUDE

    if MAX_ADAPTERS != "all":
        enabled = {n.strip() for n in MAX_ADAPTERS.split(",") if n.strip()}
        adapters = {k: v for k, v in adapters.items() if k in enabled}

    if MAX_ADAPTERS_EXCLUDE:
        excluded = {n.strip() for n in MAX_ADAPTERS_EXCLUDE.split(",") if n.strip()}
        adapters = {k: v for k, v in adapters.items() if k not in excluded}

    return adapters


# Lazy-initialized cache
_cache: dict[str, type[SourceAdapter]] | None = None


def _get_registry() -> dict[str, type[SourceAdapter]]:
    global _cache  # noqa: PLW0603
    if _cache is None:
        _cache = _filter_adapters(_discover_adapters())
    return _cache


def get_adapter(name: str) -> SourceAdapter:
    """Get a single adapter by name."""
    registry = _get_registry()
    cls = registry.get(name)
    if cls is None:
        raise KeyError(f"Unknown adapter: {name}. Available: {list(registry)}")
    return cls()


def list_adapters() -> list[str]:
    """List names of all available adapters."""
    return list(_get_registry())


def _metadata_from_class(name: str, cls: type[SourceAdapter]) -> AdapterMetadata:
    """Return registry metadata for an adapter class."""
    builtin = _BUILTIN_ADAPTER_METADATA.get(name)
    if builtin is not None:
        return builtin

    description = getattr(cls, "description", None)
    if not isinstance(description, str) or not description.strip():
        description = (cls.__doc__ or "").strip().splitlines()[0] if cls.__doc__ else ""

    config_keys = getattr(cls, "config_keys", getattr(cls, "supported_config_keys", []))
    required_keys = getattr(cls, "required_keys", getattr(cls, "required_config_keys", []))

    return AdapterMetadata(
        name=name,
        config_keys=list(config_keys or []),
        required_keys=list(required_keys or []),
        description=description,
    )


def get_adapter_metadata() -> dict[str, AdapterMetadata]:
    """Return supported config keys, required keys, and descriptions for adapters."""
    return {
        name: _metadata_from_class(name, cls)
        for name, cls in _get_registry().items()
    }


def list_adapter_metadata() -> list[AdapterMetadata]:
    """Return adapter metadata as a sorted list."""
    return sorted(get_adapter_metadata().values(), key=lambda item: item.name)


def get_all_adapters(
    source_configs: list | None = None,
) -> list[SourceAdapter]:
    """Instantiate and return adapters.

    When *source_configs* is ``None``, returns all discovered adapters with
    default configuration (backward compatible).

    When a list of ``SourceConfig`` objects (or dicts with ``adapter``,
    ``enabled``, ``params`` keys) is provided, instantiates only the listed
    adapters with their per-profile configuration.
    """
    registry = _get_registry()

    if source_configs is None:
        return [cls() for cls in registry.values()]

    adapters: list[SourceAdapter] = []
    for sc in source_configs:
        # Accept both SourceConfig objects and plain dicts
        adapter_name = sc.adapter if hasattr(sc, "adapter") else sc.get("adapter", "")
        enabled = sc.enabled if hasattr(sc, "enabled") else sc.get("enabled", True)
        if hasattr(sc, "normalized_params"):
            params = sc.normalized_params
        elif hasattr(sc, "params"):
            params = sc.params
        else:
            params = sc.get("params", {})

        if not enabled:
            continue
        cls = registry.get(adapter_name)
        if cls is None:
            logger.warning("Profile references unknown adapter: %s", adapter_name)
            continue
        adapters.append(cls(config=params))
    return adapters


def reload_registry() -> None:
    """Force re-discovery. Useful for testing."""
    global _cache  # noqa: PLW0603
    _cache = None
