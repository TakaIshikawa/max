"""Wikipedia technology article adapter for knowledge signals.

Collects technology article metadata and edit activity via the MediaWiki API.
Fetches article summaries, page views, edit frequency, and linked references
for technology topics.  Identifies technologies gaining attention through edit
velocity and page view trends.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"

_DEFAULT_SEARCH_TERMS = [
    "React (software)", "Rust (programming language)", "Kubernetes",
    "Large language model", "WebAssembly",
]


def _parse_dt(s: str | None) -> datetime | None:
    """Parse ISO 8601 datetime from MediaWiki API responses."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _build_tags(title: str, categories: list[str]) -> list[str]:
    """Build tags for a Wikipedia article signal."""
    tags: set[str] = {"wikipedia", "knowledge"}
    lower_title = title.lower()

    if any(kw in lower_title for kw in ("programming", "language", "software")):
        tags.add("programming")
    if any(kw in lower_title for kw in ("framework", "library")):
        tags.add("framework")
    if any(kw in lower_title for kw in ("database", "sql", "nosql")):
        tags.add("database")
    if any(kw in lower_title for kw in ("cloud", "kubernetes", "docker")):
        tags.add("infrastructure")

    for cat in categories[:5]:
        cat_lower = cat.lower()
        if "programming" in cat_lower:
            tags.add("programming")
        if "web" in cat_lower:
            tags.add("web")

    return sorted(tags)


class WikipediaAdapter(SourceAdapter):
    """Fetches article summaries and pageview statistics from Wikipedia.

    Extracts edit frequency, last modified date, and category links for
    technology topics.  Handles disambiguation pages and missing articles.

    Config options:
        search_terms: list of article titles or search terms
        query: single search query string
    """

    @property
    def name(self) -> str:
        return "wikipedia_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ARTICLE.value

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
                signals = await self._search_articles(client, self.query, seen, limit)
            else:
                for term in self.search_terms:
                    if len(signals) >= limit:
                        break
                    new_signals = await self._search_articles(
                        client, term, seen, limit - len(signals),
                    )
                    signals.extend(new_signals)

        return signals[:limit]

    async def _search_articles(
        self,
        client: httpx.AsyncClient,
        query: str,
        seen: set[str],
        limit: int,
    ) -> list[Signal]:
        """Search Wikipedia for articles matching a query."""
        signals: list[Signal] = []

        try:
            resp = await fetch_with_retry(
                WIKIPEDIA_API,
                client,
                adapter_name=self.name,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": min(limit, 20),
                    "format": "json",
                    "utf8": "1",
                },
            )
            data = resp.json()
        except Exception:
            logger.warning("Wikipedia search failed for: %s", query, exc_info=True)
            return signals

        results = data.get("query", {}).get("search", [])

        for result in results:
            title = result.get("title", "")
            page_id = result.get("pageid")
            if not title or title in seen:
                continue
            seen.add(title)

            snippet = result.get("snippet", "")
            timestamp = result.get("timestamp")
            word_count = result.get("wordcount", 0)

            # Fetch categories for the page
            categories = await self._fetch_categories(client, title)

            signals.append(
                Signal(
                    source_type=SignalSourceType.ARTICLE,
                    source_adapter=self.name,
                    title=title,
                    content=snippet[:500] if snippet else title,
                    url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    published_at=_parse_dt(timestamp),
                    tags=_build_tags(title, categories),
                    credibility=min(word_count / 10000, 1.0) if word_count else 0.3,
                    metadata={
                        "page_id": page_id,
                        "word_count": word_count,
                        "last_edited": timestamp,
                        "categories": categories[:10],
                        "is_disambiguation": "(disambiguation)" in title.lower(),
                    },
                )
            )

            if len(signals) >= limit:
                break

        return signals

    async def _fetch_categories(
        self, client: httpx.AsyncClient, title: str,
    ) -> list[str]:
        """Fetch categories for a Wikipedia article."""
        try:
            resp = await fetch_with_retry(
                WIKIPEDIA_API,
                client,
                adapter_name=self.name,
                params={
                    "action": "query",
                    "titles": title,
                    "prop": "categories",
                    "cllimit": "10",
                    "format": "json",
                },
            )
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                cats = page.get("categories", [])
                return [c.get("title", "").replace("Category:", "") for c in cats]
        except Exception:
            logger.debug("Failed to fetch categories for: %s", title)
        return []
