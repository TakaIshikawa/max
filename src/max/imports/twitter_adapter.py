"""Twitter/X source adapter — trending signals from developer discussions."""

from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

TWITTER_API_BASE = "https://api.twitter.com/2"
_DEFAULT_BEARER_TOKEN_ENV = "TWITTER_BEARER_TOKEN"

_DEFAULT_QUERIES = [
    "developer tools",
    "open source AI",
    "LLM agents",
    "MCP protocol",
]

_KEYWORD_TAGS = {
    "ai": ["ai", "llm", "gpt", "claude", "openai", "anthropic"],
    "agent": ["agent", "agentic", "autonomous"],
    "mcp": ["mcp", "model context protocol"],
    "rust": ["rust", "cargo"],
    "python": ["python", "pip"],
    "security": ["security", "vulnerability", "cve"],
    "open_source": ["open source", "oss", "foss"],
    "devtools": ["devtools", "developer tools", "tooling"],
}


class TwitterAdapter(SourceAdapter):
    """Fetch tweets by keywords, hashtags, or user handles via Twitter API v2."""

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
        value = self._config.get("bearer_token_env", _DEFAULT_BEARER_TOKEN_ENV)
        return value if isinstance(value, str) and value.strip() else _DEFAULT_BEARER_TOKEN_ENV

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        token = os.environ.get(self.bearer_token_env)
        if not token:
            logger.warning("Twitter bearer token not found in env var %s", self.bearer_token_env)
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "max-twitter-adapter/0.1",
            "Accept": "application/json",
        }

        signals: list[Signal] = []
        seen_ids: set[str] = set()
        queries = self.queries
        per_query = max(limit // len(queries), 5) if queries else limit

        async with httpx.AsyncClient(
            timeout=30, headers=headers, follow_redirects=True,
        ) as client:
            for query in queries:
                if len(signals) >= limit:
                    break
                await self._search_tweets(
                    client, query=query, max_results=per_query,
                    signals=signals, seen_ids=seen_ids, limit=limit,
                )

        return signals[:limit]

    async def _search_tweets(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        max_results: int,
        signals: list[Signal],
        seen_ids: set[str],
        limit: int,
    ) -> None:
        params = {
            "query": f"{query} -is:retweet lang:en",
            "max_results": min(max(max_results, 10), 100),
            "tweet.fields": "created_at,public_metrics,author_id,entities",
        }
        try:
            resp = await fetch_with_retry(
                f"{TWITTER_API_BASE}/tweets/search/recent",
                client,
                adapter_name=self.name,
                params=params,
            )
            data = resp.json()
        except (AdapterFetchError, httpx.RequestError, httpx.TimeoutException, ValueError):
            logger.warning("Twitter search failed for query: %s", query, exc_info=True)
            return

        tweets = data.get("data", [])
        if not isinstance(tweets, list):
            return

        for tweet in tweets:
            if len(signals) >= limit:
                break
            if not isinstance(tweet, dict):
                continue

            tweet_id = tweet.get("id")
            if not tweet_id or str(tweet_id) in seen_ids:
                continue

            signal = self._tweet_to_signal(tweet, query=query)
            if signal is None:
                continue

            seen_ids.add(str(tweet_id))
            signals.append(signal)

    def _tweet_to_signal(self, tweet: dict, *, query: str) -> Signal | None:
        text = tweet.get("text", "")
        if not text:
            return None

        tweet_id = str(tweet.get("id", ""))
        metrics = tweet.get("public_metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}

        likes = _int_or_zero(metrics.get("like_count"))
        retweets = _int_or_zero(metrics.get("retweet_count"))
        replies = _int_or_zero(metrics.get("reply_count"))
        quote_count = _int_or_zero(metrics.get("quote_count"))

        author_id = tweet.get("author_id")
        timestamp = _parse_twitter_timestamp(tweet.get("created_at"))
        hashtags = _extract_hashtags(tweet)

        return Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter=self.name,
            title=_title_from_text(text),
            content=text[:1000],
            url=f"https://x.com/i/status/{tweet_id}",
            author=str(author_id) if author_id else None,
            published_at=timestamp,
            tags=_extract_tags(text, query, hashtags),
            credibility=_credibility(likes=likes, retweets=retweets, replies=replies),
            metadata={
                "tweet_id": tweet_id,
                "author_id": author_id,
                "likes": likes,
                "retweets": retweets,
                "replies": replies,
                "quotes": quote_count,
                "hashtags": hashtags,
                "query": query,
            },
        )


def _int_or_zero(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _parse_twitter_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_hashtags(tweet: dict) -> list[str]:
    entities = tweet.get("entities", {})
    if not isinstance(entities, dict):
        return []
    hashtags = entities.get("hashtags", [])
    if not isinstance(hashtags, list):
        return []
    return [
        h.get("tag", "").lower()
        for h in hashtags
        if isinstance(h, dict) and h.get("tag")
    ]


def _title_from_text(text: str) -> str:
    line = " ".join(text.split())
    return line[:117] + "..." if len(line) > 120 else line


def _extract_tags(text: str, query: str, hashtags: list[str]) -> list[str]:  # noqa: ARG001
    tags: set[str] = {"twitter"}
    lower = text.lower()

    for tag, keywords in _KEYWORD_TAGS.items():
        if any(kw in lower for kw in keywords):
            tags.add(tag)

    for ht in hashtags[:5]:
        tags.add(ht)

    return sorted(tags)[:10]


def _credibility(*, likes: int, retweets: int, replies: int) -> float:
    score = (likes * 1) + (retweets * 3) + (replies * 2)
    return min(0.2 + (score / 200.0), 1.0)
