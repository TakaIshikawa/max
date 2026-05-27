"""Reddit comment thread source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class RedditCommentThreadsAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "reddit_comment_threads"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def reddit_url(self) -> str:
        return str(self._config.get("reddit_url") or "https://www.reddit.com").strip().rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        urls = _thread_urls(self._config, self.reddit_url)
        signals: list[Signal] = []
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "max-reddit-comment-threads/1.0"}) as client:
            for url in urls:
                response = await client.get(url, params={"sort": self._config.get("sort") or "confidence", "limit": int(self._config.get("max_comments_per_thread") or limit)})
                if response.status_code >= 400:
                    continue
                listings = response.json()
                title = (((listings[0] or {}).get("data") or {}).get("children") or [{}])[0].get("data", {}).get("title", "") if isinstance(listings, list) and listings else ""
                for comment in _walk_comments(listings):
                    body = str(comment.get("body") or "").strip()
                    if not body or body in {"[deleted]", "[removed]"}:
                        continue
                    signals.append(_signal(comment, title))
                    if len(signals) >= limit:
                        return signals
        return signals


def _thread_urls(config: dict[str, Any], base: str) -> list[str]:
    urls = _strings(config.get("post_urls"))
    for post_id in _strings(config.get("post_ids")):
        urls.append(f"{base}/comments/{post_id}.json")
    for subreddit in _strings(config.get("subreddits")):
        urls.append(f"{base}/r/{subreddit}/comments.json")
    return urls


def _walk_comments(payload: Any) -> list[dict[str, Any]]:
    roots = payload[1:] if isinstance(payload, list) else [payload]
    found: list[dict[str, Any]] = []
    def walk(node: Any, depth: int = 0) -> None:
        if isinstance(node, dict):
            data = node.get("data") if isinstance(node.get("data"), dict) else node
            if data.get("body") is not None:
                data.setdefault("depth", depth)
                found.append(data)
            replies = data.get("replies")
            children = ((replies or {}).get("data") or {}).get("children") if isinstance(replies, dict) else None
            for child in children or data.get("children") or []:
                walk(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                walk(child, depth)
    walk(roots)
    return found


def _signal(comment: dict[str, Any], title: str) -> Signal:
    permalink = comment.get("permalink") or ""
    url = f"https://www.reddit.com{permalink}" if str(permalink).startswith("/") else str(permalink)
    return Signal(
        id=_id("reddit-comment", comment.get("id")),
        source_type=SignalSourceType.FORUM,
        source_adapter="reddit_comment_threads",
        title=f"Reddit comment in {title or comment.get('subreddit') or 'thread'}",
        content=str(comment.get("body") or "")[:500],
        url=url,
        author=comment.get("author"),
        published_at=_dt(comment.get("created_utc")),
        tags=["reddit", str(comment.get("subreddit") or "").lower()],
        credibility=min(max(float(comment.get("score") or 0) / 100, 0.1), 1.0),
        metadata={"comment_id": comment.get("id"), "score": comment.get("score") or 0, "depth": comment.get("depth") or 0, "parent_id": comment.get("parent_id") or "", "subreddit": comment.get("subreddit") or "", "permalink": permalink, "thread_title": title, "source_url": url, "signal_role": "problem"},
    )


def _strings(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    return [str(v).strip() for v in values if str(v).strip()]


def _dt(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


def _id(*parts: object) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16]
