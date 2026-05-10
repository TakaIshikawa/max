"""Twitter/X source adapter — trending topics, hashtags, and developer discussions."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

TWITTER_API_BASE = "https://api.twitter.com/2"

_DEFAULT_QUERIES = [
    "developer tools",
    "open source",
    "machine learning",
    "AI agents",
    "MCP protocol",
]


class TwitterAdapter(SourceAdapter):
    """Collects trending signals from Twitter/X API v2.

    Fetches tweets by hashtags, keywords, or user handles and extracts
    engagement metrics to identify emerging technologies and community sentiment.
    """

    @property
    def name(self) -> str:
        return "twitter"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def _bearer_token(self) -> str | None:
        return self._config.get("bearer_token")

    @property
    def _api_base(self) -> str:
        return self._config.get("api_base", TWITTER_API_BASE)

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        per_query = max(limit // len(self.queries), 3)
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(
            timeout=30,
            headers=self._auth_headers(),
            follow_redirects=True,
        ) as client:
            for query in self.queries:
                if len(signals) >= limit:
                    break
                try:
                    resp = await fetch_with_retry(
                        f"{self._api_base}/tweets/search/recent",
                        client,
                        adapter_name=self.name,
                        params={
                            "query": query,
                            "max_results": per_query,
                            "tweet.fields": "created_at,public_metrics,author_id",
                        },
                    )
                    data = resp.json()
                except AdapterFetchError:
                    logger.warning(
                        "Twitter fetch failed for query=%s", query, exc_info=True,
                    )
                    continue
                except (ValueError, KeyError, TypeError):
                    logger.warning(
                        "Twitter parse failed for query=%s", query, exc_info=True,
                    )
                    continue

                for tweet in data.get("data", []):
                    tweet_id = tweet.get("id", "")
                    if not tweet_id or tweet_id in seen_ids:
                        continue
                    seen_ids.add(tweet_id)

                    text = tweet.get("text", "")
                    if not text:
                        continue

                    metrics = tweet.get("public_metrics", {})
                    likes = _safe_int(metrics.get("like_count", 0))
                    retweets = _safe_int(metrics.get("retweet_count", 0))
                    replies = _safe_int(metrics.get("reply_count", 0))
                    engagement = likes + retweets * 2 + replies

                    published_at = _parse_iso(tweet.get("created_at"))

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.FORUM,
                            source_adapter=self.name,
                            title=text[:120],
                            content=text,
                            url=f"https://x.com/i/status/{tweet_id}",
                            author=tweet.get("author_id"),
                            published_at=published_at,
                            tags=_extract_tags(text, query),
                            credibility=min(engagement / 500, 1.0),
                            metadata={
                                "tweet_id": tweet_id,
                                "search_query": query,
                                "like_count": likes,
                                "retweet_count": retweets,
                                "reply_count": replies,
                                "engagement_score": engagement,
                            },
                        )
                    )

        return signals[:limit]


def _safe_int(value: object) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_tags(text: str, query: str) -> list[str]:
    tags: list[str] = ["twitter"]
    lower = text.lower()

    query_tag = query.lower().replace(" ", "-")
    if query_tag not in tags:
        tags.append(query_tag)

    tech_keywords = {
        "ai": ["ai", "artificial intelligence", "llm", "gpt", "machine learning"],
        "open-source": ["open source", "oss", "foss"],
        "devtools": ["developer tools", "devtools", "ide"],
        "rust": ["rust", "cargo"],
        "python": ["python", "pip"],
        "mcp": ["mcp", "model context protocol"],
    }
    for tag, terms in tech_keywords.items():
        if any(t in lower for t in terms) and tag not in tags:
            tags.append(tag)

    return tags
