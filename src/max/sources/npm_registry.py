"""npm registry source adapter — trending/new packages."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

NPM_SEARCH = "https://registry.npmjs.org/-/v1/search"


_DEFAULT_QUERIES = ["mcp server", "ai agent", "llm tool", "claude"]


class NpmRegistryAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "npm_registry"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._config.get("queries", _DEFAULT_QUERIES)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        queries = self.queries

        async with httpx.AsyncClient(timeout=30) as client:
            for query in queries:
                if len(signals) >= limit:
                    break

                try:
                    resp = await fetch_with_retry(
                        NPM_SEARCH,
                        client,
                        adapter_name=self.name,
                        params={"text": query, "size": min(10, limit - len(signals))},
                    )
                except AdapterFetchError as e:
                    logger.warning(
                        "%s: failed to fetch search results for query '%s': %s",
                        self.name,
                        query,
                        e,
                    )
                    continue

                try:
                    data = resp.json()
                except (ValueError, KeyError) as e:
                    logger.warning(
                        "%s: failed to parse JSON response for query '%s': %s",
                        self.name,
                        query,
                        e,
                    )
                    continue

                for obj in data.get("objects", []):
                    try:
                        pkg = obj.get("package", {})
                        name = pkg.get("name", "")
                        description = pkg.get("description", "")
                        version = pkg.get("version", "")

                        # Compute credibility from search score
                        search_score = obj.get("searchScore", 0)
                        credibility = min(search_score / 100_000, 1.0)

                        published = pkg.get("date")
                        published_at = (
                            datetime.fromisoformat(published.replace("Z", "+00:00"))
                            if published
                            else None
                        )

                        signals.append(
                            Signal(
                                source_type=SignalSourceType.REGISTRY,
                                source_adapter=self.name,
                                title=f"{name}@{version}",
                                content=description or name,
                                url=f"https://www.npmjs.com/package/{name}",
                                author=pkg.get("publisher", {}).get("username"),
                                published_at=published_at,
                                tags=pkg.get("keywords", [])[:10],
                                credibility=credibility,
                                metadata={
                                    "npm_name": name,
                                    "version": version,
                                    "search_query": query,
                                },
                            )
                        )
                    except (KeyError, TypeError, ValueError) as e:
                        logger.warning(
                            "%s: failed to parse package object for query '%s': %s",
                            self.name,
                            query,
                            e,
                        )
                        continue

        return signals[:limit]
