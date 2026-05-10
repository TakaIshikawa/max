"""W3Techs source adapter for web technology usage signals.

Collects web technology usage statistics from W3Techs.  Parses public data on
server-side languages, CMS platforms, JavaScript libraries, and web server
market share.  Extracts adoption percentages and trend data for technology
market positioning.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

W3TECHS_BASE = "https://w3techs.com"

_DEFAULT_CATEGORIES = [
    "programming_languages",
    "content_management",
    "web_servers",
    "javascript_libraries",
]

_CATEGORY_URLS = {
    "programming_languages": "/technologies/overview/programming_language",
    "content_management": "/technologies/overview/content_management",
    "web_servers": "/technologies/overview/web_server",
    "javascript_libraries": "/technologies/overview/javascript_library",
}

_PERCENTAGE_PATTERN = re.compile(
    r"([A-Za-z][A-Za-z0-9\s.#+/-]+?)\s+(\d+(?:\.\d+)?)\s*%",
)


def _build_tags(tech_name: str, category: str) -> list[str]:
    """Build tags for a W3Techs signal."""
    tags: set[str] = {"w3techs", "market-share"}
    if category:
        tags.add(category.replace("_", "-"))

    lower = tech_name.lower()
    if any(kw in lower for kw in ("php", "python", "ruby", "java", "node")):
        tags.add("programming")
    if any(kw in lower for kw in ("wordpress", "drupal", "joomla", "shopify")):
        tags.add("cms")
    if any(kw in lower for kw in ("nginx", "apache", "litespeed")):
        tags.add("webserver")
    if any(kw in lower for kw in ("jquery", "react", "vue", "angular")):
        tags.add("javascript")

    return sorted(tags)


class W3TechsAdapter(SourceAdapter):
    """Fetches technology usage percentages from W3Techs.

    Extracts market share for languages, CMS, web servers, and JS frameworks.
    Handles HTML parsing and data normalization.

    Config options:
        categories: list of W3Techs categories to fetch
        query: single category to fetch
    """

    @property
    def name(self) -> str:
        return "w3techs_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    @property
    def query(self) -> str | None:
        q = self._config.get("query")
        return q if isinstance(q, str) else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            categories = [self.query] if self.query else self.categories
            for category in categories:
                if len(signals) >= limit:
                    break
                new_signals = await self._fetch_category(
                    client, category, seen, limit - len(signals),
                )
                signals.extend(new_signals)

        return signals[:limit]

    async def _fetch_category(
        self,
        client: httpx.AsyncClient,
        category: str,
        seen: set[str],
        limit: int,
    ) -> list[Signal]:
        """Fetch technology usage data for a category."""
        signals: list[Signal] = []
        url_path = _CATEGORY_URLS.get(category, f"/technologies/overview/{category}")

        try:
            resp = await fetch_with_retry(
                f"{W3TECHS_BASE}{url_path}",
                client,
                adapter_name=self.name,
            )
            html = resp.text
        except Exception:
            logger.warning("W3Techs fetch failed for: %s", category, exc_info=True)
            return signals

        entries = self._parse_usage_data(html)

        for tech_name, percentage in entries:
            key = f"{category}:{tech_name}"
            if key in seen:
                continue
            seen.add(key)

            signals.append(
                Signal(
                    source_type=SignalSourceType.MARKET,
                    source_adapter=self.name,
                    title=f"{tech_name} - {percentage}% market share",
                    content=f"{tech_name} is used by {percentage}% of websites in the {category.replace('_', ' ')} category.",
                    url=f"{W3TECHS_BASE}{url_path}",
                    published_at=datetime.now(timezone.utc),
                    tags=_build_tags(tech_name, category),
                    credibility=0.8,  # W3Techs is a reputable source
                    metadata={
                        "technology": tech_name,
                        "category": category,
                        "percentage": percentage,
                        "market_position": len(signals) + 1,
                    },
                )
            )

            if len(signals) >= limit:
                break

        return signals

    def _parse_usage_data(self, html: str) -> list[tuple[str, float]]:
        """Parse technology usage percentages from HTML content.

        Returns list of (technology_name, percentage) tuples sorted by
        percentage descending.
        """
        entries: list[tuple[str, float]] = []

        for match in _PERCENTAGE_PATTERN.finditer(html):
            name = match.group(1).strip()
            try:
                pct = float(match.group(2))
            except ValueError:
                continue
            if name and pct > 0:
                entries.append((name, pct))

        # Deduplicate keeping highest percentage per tech
        best: dict[str, float] = {}
        for name, pct in entries:
            if name not in best or pct > best[name]:
                best[name] = pct

        return sorted(best.items(), key=lambda x: x[1], reverse=True)
