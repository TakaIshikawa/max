"""Google Trends source adapter for search interest signals.

Collects search interest and trending topic data via the pytrends library.
Fetches interest over time, related queries, and regional interest to
identify rising search terms and technology adoption curves based on search
volume.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_DEFAULT_KEYWORDS = ["AI agent", "MCP protocol", "LLM framework", "developer tools"]


def _build_tags(keyword: str) -> list[str]:
    """Build normalized tags from keyword."""
    tags: set[str] = set()
    kw_map = {
        "ai": "ai",
        "agent": "agent",
        "llm": "llm",
        "mcp": "mcp",
        "developer": "devtools",
        "saas": "saas",
        "cloud": "cloud",
        "security": "security",
        "ml": "ml",
        "machine learning": "ml",
    }
    kw_lower = keyword.lower()
    for term, tag in kw_map.items():
        if term in kw_lower:
            tags.add(tag)
    tags.add("gtrends")
    return sorted(tags)[:10]


class GTrendsAdapter(SourceAdapter):
    """Fetches interest over time and related queries for keywords.

    Supports keyword comparison and regional filtering.
    Handles API rate limits and session management via pytrends.
    """

    @property
    def name(self) -> str:
        return "gtrends_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def keywords(self) -> list[str]:
        return self._configured_terms("keywords", _DEFAULT_KEYWORDS)

    @property
    def timeframe(self) -> str:
        tf = self._config.get("timeframe", "today 3-m")
        return tf if isinstance(tf, str) else "today 3-m"

    @property
    def geo(self) -> str:
        g = self._config.get("geo", "")
        return g if isinstance(g, str) else ""

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []

        try:
            from pytrends.request import TrendReq
        except ImportError:
            logger.warning("pytrends not installed — skipping Google Trends fetch")
            return signals

        pytrends = TrendReq(hl="en-US", tz=360)

        # Process keywords in batches of 5 (pytrends limit)
        keyword_batches = [
            self.keywords[i : i + 5] for i in range(0, len(self.keywords), 5)
        ]

        for batch in keyword_batches:
            if len(signals) >= limit:
                break

            try:
                pytrends.build_payload(
                    batch,
                    timeframe=self.timeframe,
                    geo=self.geo,
                )

                interest_df = pytrends.interest_over_time()
            except Exception:
                logger.warning(
                    "Google Trends fetch failed for keywords: %s",
                    batch,
                    exc_info=True,
                )
                continue

            if interest_df is None or interest_df.empty:
                continue

            # Drop isPartial column if present
            if "isPartial" in interest_df.columns:
                interest_df = interest_df.drop(columns=["isPartial"])

            for keyword in batch:
                if keyword not in interest_df.columns:
                    continue
                if len(signals) >= limit:
                    break

                series = interest_df[keyword]
                current_value = int(series.iloc[-1]) if len(series) > 0 else 0
                avg_value = float(series.mean()) if len(series) > 0 else 0
                max_value = int(series.max()) if len(series) > 0 else 0

                # Fetch related queries for this keyword
                related: list[dict] = []
                try:
                    pytrends.build_payload(
                        [keyword],
                        timeframe=self.timeframe,
                        geo=self.geo,
                    )
                    related_queries = pytrends.related_queries()
                    kw_related = related_queries.get(keyword, {})
                    rising_df = kw_related.get("rising")
                    if rising_df is not None and not rising_df.empty:
                        for _, row in rising_df.head(5).iterrows():
                            related.append({
                                "query": row.get("query", ""),
                                "value": int(row.get("value", 0)),
                            })
                except Exception:
                    logger.debug(
                        "Failed to fetch related queries for: %s", keyword,
                    )

                signals.append(
                    Signal(
                        source_type=SignalSourceType.TRENDING,
                        source_adapter=self.name,
                        title=keyword,
                        content=f"Search interest for '{keyword}': current={current_value}, avg={avg_value:.0f}, max={max_value}",
                        url=f"https://trends.google.com/trends/explore?q={keyword.replace(' ', '%20')}",
                        author=None,
                        published_at=datetime.now(timezone.utc),
                        tags=_build_tags(keyword),
                        credibility=min(current_value / 100, 1.0),
                        metadata={
                            "keyword": keyword,
                            "current_interest": current_value,
                            "average_interest": round(avg_value, 1),
                            "max_interest": max_value,
                            "timeframe": self.timeframe,
                            "geo": self.geo or "worldwide",
                            "related_rising": related,
                            "data_points": len(series),
                        },
                    )
                )

        return signals[:limit]
