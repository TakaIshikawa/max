"""Twitter/X source adapter — trending topics, hashtags, and developer discussions."""

from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

TWITTER_API_V2 = "https://api.twitter.com/2"

_DEFAULT_QUERIES = [
    "#ai",
    "#llm",
    "#mcp",
    "#developer",
    "#opensource",
    "#python",
]

_DEFAULT_BEARER_TOKEN_ENV = "TWITTER_BEARER_TOKEN"

_KEYWORD_TAGS: dict[str, str] = {
    "agent": "agent",
    "llm": "llm",
    "mcp": "mcp",
    "openai": "openai",
    "langchain": "langchain",
    "rag": "rag",
    "embedding": "embedding",
    "claude": "claude",
    "anthropic": "anthropic",
    "rust": "rust",
    "python": "python",
    "typescript": "typescript",
}


def _extract_tags(text: str, query: str) -> list[str]:
    """Build signal tags from tweet text and search query."""
    tags: set[str] = {"twitter"}

    query_tag = query.strip().lstrip("#").lower().replace(" ", "-")
    if query_tag:
        tags.add(query_tag)

    text_lower = text.lower()
    for keyword, tag in _KEYWORD_TAGS.items():
        if keyword in text_lower:
            tags.add(tag)

    return sorted(tags)[:10]


def _parse_datetime(date_str: str | None) -> datetime | None:
    """Parse ISO 8601 datetime from Twitter API v2."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _title_from_text(text: str) -> str:
    """Create a title from tweet text, truncating if needed."""
    title = " ".join(text.split())
    if len(title) <= 100:
        return title
    return f"{title[:97].rstrip()}..."


def _engagement_credibility(
    likes: int, retweets: int, replies: int, quotes: int,
) -> float:
    """Compute credibility score from engagement metrics."""
    engagement = likes + (retweets * 2) + replies + quotes
    return min(round(0.1 + (engagement / 500), 3), 1.0)


class TwitterAdapter(SourceAdapter):
    """Fetch tweets by hashtags, keywords, or user handles via Twitter API v2."""

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
    def bearer_token_env(self) -> str:
        return self._config.get("bearer_token_env", _DEFAULT_BEARER_TOKEN_ENV)

    @property
    def max_results_per_query(self) -> int:
        return min(self._config.get("max_results_per_query", 10), 100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        bearer_token = os.environ.get(self.bearer_token_env, "")
        if not bearer_token:
            logger.warning(
                "%s: no bearer token found in env var %s",
                self.name, self.bearer_token_env,
            )
            return []

        signals: list[Signal] = []
        seen_ids: set[str] = set()
        queries = self.queries
        per_query = max(limit // len(queries), 3) if queries else limit

        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "max-twitter-adapter/0.1",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for query in queries:
                if len(signals) >= limit:
                    break

                tweets = await self._search_tweets(
                    client,
                    query=query,
                    max_results=min(per_query, self.max_results_per_query),
                )
                if tweets is None:
                    continue

                for tweet_data, metrics in tweets:
                    if len(signals) >= limit:
                        break

                    tweet_id = tweet_data.get("id")
                    if not tweet_id or tweet_id in seen_ids:
                        continue
                    seen_ids.add(tweet_id)

                    text = tweet_data.get("text", "")
                    author_id = tweet_data.get("author_id")
                    likes = metrics.get("like_count", 0)
                    retweets = metrics.get("retweet_count", 0)
                    replies = metrics.get("reply_count", 0)
                    quotes = metrics.get("quote_count", 0)

                    signals.append(Signal(
                        source_type=SignalSourceType.FORUM,
                        source_adapter=self.name,
                        title=_title_from_text(text),
                        content=text[:500],
                        url=f"https://x.com/i/status/{tweet_id}",
                        author=author_id,
                        published_at=_parse_datetime(tweet_data.get("created_at")),
                        tags=_extract_tags(text, query),
                        credibility=_engagement_credibility(
                            likes, retweets, replies, quotes,
                        ),
                        metadata={
                            "tweet_id": tweet_id,
                            "author_id": author_id,
                            "likes": likes,
                            "retweets": retweets,
                            "replies": replies,
                            "quotes": quotes,
                            "search_query": query,
                        },
                    ))

        return signals[:limit]

    async def _search_tweets(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        max_results: int,
    ) -> list[tuple[dict, dict]] | None:
        """Search recent tweets, returning (tweet_data, public_metrics) pairs."""
        try:
            resp = await fetch_with_retry(
                f"{TWITTER_API_V2}/tweets/search/recent",
                client,
                adapter_name=self.name,
                params={
                    "query": query,
                    "max_results": max(max_results, 10),
                    "tweet.fields": "created_at,author_id,public_metrics",
                },
            )
            data = resp.json()
        except Exception:
            logger.warning(
                "%s: failed to search tweets for query '%s'",
                self.name, query, exc_info=True,
            )
            return None

        if not isinstance(data, dict):
            return None

        tweets = data.get("data")
        if not isinstance(tweets, list):
            return None

        results: list[tuple[dict, dict]] = []
        for tweet in tweets:
            if not isinstance(tweet, dict):
                continue
            metrics = tweet.get("public_metrics", {})
            if not isinstance(metrics, dict):
                metrics = {}
            results.append((tweet, metrics))

        return results
