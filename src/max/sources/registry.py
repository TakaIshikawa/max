"""Adapter registry — discover and instantiate source adapters.

Adapters are discovered via entry_points (group: max.adapters) for installed
packages, with a fallback to built-in imports for dev mode.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging

from max.sources.base import SourceAdapter

logger = logging.getLogger(__name__)

# Fallback mapping for dev mode (when package is not pip-installed).
_BUILTIN_ADAPTERS: dict[str, str] = {
    "hackernews": "max.sources.hackernews:HackerNewsAdapter",
    "npm_registry": "max.sources.npm_registry:NpmRegistryAdapter",
    "reddit": "max.sources.reddit:RedditAdapter",
    "github": "max.sources.github:GitHubAdapter",
    "pypi_registry": "max.sources.pypi_registry:PyPIRegistryAdapter",
    "github_issues": "max.sources.github_issues:GitHubIssuesAdapter",
    "security_advisories": "max.sources.security_advisories:SecurityAdvisoriesAdapter",
    "product_hunt": "max.sources.product_hunt:ProductHuntAdapter",
    "stackoverflow": "max.sources.stackoverflow:StackOverflowAdapter",
    "arxiv": "max.sources.arxiv:ArxivAdapter",
    "devto": "max.sources.devto:DevtoAdapter",
    "pubmed": "max.sources.pubmed:PubMedAdapter",
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
        params = sc.params if hasattr(sc, "params") else sc.get("params", {})

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
