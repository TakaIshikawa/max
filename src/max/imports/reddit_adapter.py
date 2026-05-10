"""Reddit source adapter — community signals from subreddit discussions."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_DEFAULT_SUBREDDITS = [
    "programming",
    "MachineLearning",
    "LocalLLaMA",
    "ChatGPT",
    "artificial",
    "devops",
    "ExperiencedDevs",
]

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_KEYWORD_TAGS: dict[str, list[str]] = {
    "ai": ["ai", "llm", "gpt", "claude", "openai", "anthropic"],
    "agent": ["agent", "agentic", "autonomous"],
    "mcp": ["mcp", "model context protocol"],
    "rust": ["rust", "cargo"],
    "python": ["python", "pip"],
    "security": ["security", "vulnerability", "cve", "exploit"],
    "open_source": ["open source", "oss", "foss"],
}

_SUBREDDIT_TAGS: dict[str, str] = {
    "MachineLearning": "ml",
    "LocalLLaMA": "llm",
    "ChatGPT": "ai",
    "artificial": "ai",
    "devops": "devops",
    "programming": "programming",
    "ExperiencedDevs": "devtools",
}


def _extract_tags(title: str, subreddit: str) -> list[str]:
    """Extract tags from post title and subreddit context."""
    tags: list[str] = []
    lower = title.lower()

    sub_tag = _SUBREDDIT_TAGS.get(subreddit)
    if sub_tag:
        tags.append(sub_tag)

    for tag, terms in _KEYWORD_TAGS.items():
        if any(t in lower for t in terms) and tag not in tags:
            tags.append(tag)

    tags.append("reddit")
    return tags[:10]


class RedditAdapter(SourceAdapter):
    """Fetch posts and comments from specified subreddits."""

    @property
    def name(self) -> str:
        return "reddit_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def subreddits(self) -> list[str]:
        return self._configured_terms("subreddits", _DEFAULT_SUBREDDITS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        subreddits = self.subreddits
        per_sub = max(limit // len(subreddits), 3)

        for i, subreddit in enumerate(subreddits):
            if len(signals) >= limit:
                break
            if i > 0:
                await asyncio.sleep(2)

            async with httpx.AsyncClient(
                timeout=30,
                headers=_BROWSER_HEADERS,
                follow_redirects=True,
            ) as client:
                try:
                    resp = await fetch_with_retry(
                        f"https://old.reddit.com/r/{subreddit}/hot.json",
                        client,
                        adapter_name=self.name,
                        params={"limit": per_sub},
                    )
                    data = resp.json()
                except Exception:
                    logger.warning(
                        "Reddit fetch failed for r/%s", subreddit, exc_info=True,
                    )
                    continue

                if not isinstance(data, dict):
                    continue

                for child in data.get("data", {}).get("children", []):
                    if len(signals) >= limit:
                        break
                    post = child.get("data", {})
                    if post.get("stickied"):
                        continue

                    title = post.get("title", "")
                    selftext = post.get("selftext", "")
                    score = post.get("score", 0)
                    permalink = f"https://www.reddit.com{post.get('permalink', '')}"

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.FORUM,
                            source_adapter=self.name,
                            title=title,
                            content=selftext[:1000] if selftext else title,
                            url=permalink,
                            author=post.get("author"),
                            published_at=datetime.fromtimestamp(
                                post.get("created_utc", 0), tz=timezone.utc,
                            ),
                            tags=_extract_tags(title, subreddit),
                            credibility=min(score / 1000, 1.0),
                            metadata={
                                "subreddit": subreddit,
                                "score": score,
                                "num_comments": post.get("num_comments", 0),
                                "link_url": post.get("url"),
                            },
                        )
                    )

        return signals[:limit]
