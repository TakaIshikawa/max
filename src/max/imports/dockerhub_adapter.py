"""Docker Hub source adapter for container image signals.

Collects container image popularity and ecosystem signals via the Docker Hub
API.  Fetches image pull counts, star ratings, and tag activity.  Identifies
trending base images and containerization patterns across the ecosystem.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DOCKERHUB_API = "https://hub.docker.com/v2"

_DEFAULT_NAMESPACES = ["library"]
_DEFAULT_SEARCH_TERMS = ["python", "node", "golang", "rust", "ubuntu"]


def _parse_dt(s: str | None) -> datetime | None:
    """Parse ISO 8601 datetime from Docker Hub API responses."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _build_tags(name: str, namespace: str) -> list[str]:
    """Build tags for a Docker Hub image signal."""
    tags: set[str] = {"docker", "container"}
    if namespace == "library":
        tags.add("official")
    image_map = {
        "python": "python",
        "node": "typescript",
        "golang": "go",
        "rust": "rust",
        "ubuntu": "linux",
        "alpine": "linux",
        "debian": "linux",
        "postgres": "database",
        "mysql": "database",
        "redis": "database",
        "nginx": "webserver",
    }
    mapped = image_map.get(name.lower())
    if mapped:
        tags.add(mapped)
    return sorted(tags)


class DockerHubAdapter(SourceAdapter):
    """Fetches image metadata and pull statistics from Docker Hub.

    Extracts star count, pull count, tags, and last updated timestamps.
    Handles API pagination and unauthenticated rate limits.

    Config options:
        namespaces: list of Docker Hub namespaces to search (default: ["library"])
        search_terms: list of image search terms
        query: search query string
    """

    @property
    def name(self) -> str:
        return "dockerhub_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def namespaces(self) -> list[str]:
        return self._configured_terms("namespaces", _DEFAULT_NAMESPACES)

    @property
    def search_terms(self) -> list[str]:
        return self._configured_terms("search_terms", _DEFAULT_SEARCH_TERMS)

    @property
    def query(self) -> str | None:
        q = self._config.get("query")
        return q if isinstance(q, str) else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            if self.query:
                signals = await self._search_images(client, self.query, seen, limit)
            else:
                for term in self.search_terms:
                    if len(signals) >= limit:
                        break
                    new_signals = await self._search_images(
                        client, term, seen, limit - len(signals),
                    )
                    signals.extend(new_signals)

        return signals[:limit]

    async def _search_images(
        self,
        client: httpx.AsyncClient,
        query: str,
        seen: set[str],
        limit: int,
    ) -> list[Signal]:
        """Search Docker Hub for images matching a query."""
        signals: list[Signal] = []

        try:
            resp = await fetch_with_retry(
                f"{DOCKERHUB_API}/search/repositories/",
                client,
                adapter_name=self.name,
                params={
                    "query": query,
                    "page_size": min(limit, 25),
                },
            )
            data = resp.json()
        except Exception:
            logger.warning("Docker Hub search failed for: %s", query, exc_info=True)
            return signals

        for result in data.get("results", []):
            repo_name = result.get("repo_name", "")
            if not repo_name or repo_name in seen:
                continue
            seen.add(repo_name)

            namespace = repo_name.split("/")[0] if "/" in repo_name else "library"
            short_name = repo_name.split("/")[-1]
            pull_count = result.get("pull_count", 0)
            star_count = result.get("star_count", 0)

            signals.append(
                Signal(
                    source_type=SignalSourceType.REGISTRY,
                    source_adapter=self.name,
                    title=repo_name,
                    content=(result.get("short_description") or repo_name)[:500],
                    url=f"https://hub.docker.com/r/{repo_name}" if "/" in repo_name else f"https://hub.docker.com/_/{repo_name}",
                    published_at=_parse_dt(result.get("last_updated")),
                    tags=_build_tags(short_name, namespace),
                    credibility=min(pull_count / 1_000_000_000, 1.0),
                    metadata={
                        "pull_count": pull_count,
                        "star_count": star_count,
                        "is_official": result.get("is_official", False),
                        "is_automated": result.get("is_automated", False),
                        "namespace": namespace,
                        "last_updated": result.get("last_updated"),
                    },
                )
            )

            if len(signals) >= limit:
                break

        return signals
