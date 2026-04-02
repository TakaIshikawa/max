"""Reddit source adapter — top posts from developer/AI subreddits."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

_DEFAULT_SUBREDDITS = [
    "programming",
    "MachineLearning",
    "LocalLLaMA",
    "ChatGPT",
    "artificial",
    "devops",
    "ExperiencedDevs",
]

USER_AGENT = "max-idea-engine/0.1.0"


class RedditAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "reddit"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def subreddits(self) -> list[str]:
        return self._config.get("subreddits", _DEFAULT_SUBREDDITS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        subreddits = self.subreddits
        per_sub = max(limit // len(subreddits), 3)

        async with httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for subreddit in subreddits:
                if len(signals) >= limit:
                    break
                try:
                    resp = await client.get(
                        f"https://www.reddit.com/r/{subreddit}/hot.json",
                        params={"limit": per_sub},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    continue

                for child in data.get("data", {}).get("children", []):
                    post = child.get("data", {})
                    if post.get("stickied"):
                        continue

                    title = post.get("title", "")
                    selftext = post.get("selftext", "")
                    score = post.get("score", 0)
                    url = post.get("url", "")
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
                                post.get("created_utc", 0), tz=timezone.utc
                            ),
                            tags=_extract_tags(title, subreddit),
                            credibility=min(score / 1000, 1.0),
                            metadata={
                                "subreddit": subreddit,
                                "score": score,
                                "num_comments": post.get("num_comments", 0),
                                "link_url": url if url != permalink else None,
                            },
                        )
                    )

        return signals[:limit]


def _extract_tags(title: str, subreddit: str) -> list[str]:
    """Extract tags from title and subreddit context."""
    tags: list[str] = []
    lower = title.lower()

    # Subreddit-based tags
    sub_tags = {
        "MachineLearning": "ml",
        "LocalLLaMA": "llm",
        "ChatGPT": "ai",
        "artificial": "ai",
        "devops": "devops",
        "programming": "programming",
        "ExperiencedDevs": "devtools",
    }
    if subreddit in sub_tags:
        tags.append(sub_tags[subreddit])

    # Keyword tags
    keywords = {
        "ai": ["ai", "llm", "gpt", "claude", "openai", "anthropic"],
        "agent": ["agent", "agentic", "autonomous"],
        "mcp": ["mcp", "model context protocol"],
        "rust": ["rust", "cargo"],
        "python": ["python", "pip"],
        "security": ["security", "vulnerability", "cve", "exploit"],
        "open_source": ["open source", "oss", "foss"],
    }
    for tag, terms in keywords.items():
        if any(t in lower for t in terms) and tag not in tags:
            tags.append(tag)

    return tags
