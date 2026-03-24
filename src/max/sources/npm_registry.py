"""npm registry source adapter — trending/new packages."""

from __future__ import annotations

from datetime import datetime

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

NPM_SEARCH = "https://registry.npmjs.org/-/v1/search"


class NpmRegistryAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "npm_registry"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        queries = ["mcp server", "ai agent", "llm tool", "claude"]

        async with httpx.AsyncClient(timeout=30) as client:
            for query in queries:
                if len(signals) >= limit:
                    break
                resp = await client.get(
                    NPM_SEARCH,
                    params={"text": query, "size": min(10, limit - len(signals))},
                )
                resp.raise_for_status()
                data = resp.json()

                for obj in data.get("objects", []):
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

        return signals[:limit]
