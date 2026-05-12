"""Libraries.io project source adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

SEARCH_URL = "https://libraries.io/api/search"
DEFAULT_QUERIES = ["mcp", "ai agent", "llm"]


class LibrariesIoAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "libraries_io"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", DEFAULT_QUERIES)

    @property
    def platforms(self) -> list[str]:
        configured = self._config.get("platforms")
        if configured is None:
            return []
        return [str(value).strip() for value in configured if str(value).strip()]

    @property
    def api_key(self) -> str | None:
        value = self._config.get("api_key") or os.getenv("LIBRARIES_IO_API_KEY")
        text = str(value).strip() if value else ""
        return text or None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        max_items = int(self._config.get("max_items") or limit)
        target = min(limit, max_items)
        signals: list[Signal] = []
        seen: set[str] = set()
        platforms = self.platforms or [None]
        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                for platform in platforms:
                    if len(signals) >= target:
                        break
                    params: dict[str, Any] = {"q": query, "per_page": min(30, target - len(signals))}
                    if platform:
                        params["platforms"] = platform
                    if self.api_key:
                        params["api_key"] = self.api_key
                    try:
                        response = await fetch_with_retry(SEARCH_URL, client, adapter_name=self.name, params=params)
                        data = response.json()
                    except (AdapterFetchError, httpx.HTTPError, ValueError) as exc:
                        logger.warning("%s: failed to fetch query %r platform %r: %s", self.name, query, platform, exc)
                        continue
                    if not isinstance(data, list):
                        continue
                    for project in data:
                        if not isinstance(project, dict):
                            continue
                        key = str(project.get("repository_url") or project.get("url") or project.get("name") or "").strip()
                        if not key or key in seen:
                            continue
                        seen.add(key)
                        signals.append(_signal(project, query=query))
                        if len(signals) >= target:
                            break
        return signals


def _signal(project: dict[str, Any], *, query: str) -> Signal:
    name = str(project.get("name") or project.get("full_name") or "Unknown project")
    description = str(project.get("description") or name)
    stars = _int(project.get("stars"))
    rank = _int(project.get("rank"))
    credibility = min(1.0, 0.3 + min(stars, 10_000) / 20_000 + (0.2 if rank and rank < 1000 else 0.0))
    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter="libraries_io",
        title=name,
        content=description,
        url=str(project.get("repository_url") or project.get("url") or ""),
        author=project.get("package_manager_url"),
        published_at=_date(project.get("latest_release_published_at")),
        tags=[value for value in [project.get("platform"), project.get("language")] if value],
        credibility=credibility,
        metadata={
            "platform": project.get("platform"),
            "language": project.get("language"),
            "rank": rank,
            "stars": stars,
            "forks": _int(project.get("forks")),
            "dependent_repos_count": _int(project.get("dependent_repos_count")),
            "search_query": query,
            "normalized_licenses": project.get("normalized_licenses"),
        },
    )


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _date(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
