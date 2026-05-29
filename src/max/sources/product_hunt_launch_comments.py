"""Product Hunt launch comments source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

QUERY = """
query($id: ID, $slug: String, $first: Int!) {
  post(id: $id, slug: $slug) {
    id
    slug
    name
    tagline
    url
    comments(first: $first) {
      edges { node { id body createdAt votesCount user { username isMaker } maker } }
    }
  }
}
"""


class ProductHuntLaunchCommentsAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "product_hunt_launch_comments"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def api_url(self) -> str:
        return str(self._config.get("api_url") or "https://api.producthunt.com/v2/api/graphql").strip()

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        headers = {"Content-Type": "application/json"}
        if self._config.get("token"):
            headers["Authorization"] = f"Bearer {self._config['token']}"
        max_comments = int(self._config.get("max_comments") or limit)
        signals: list[Signal] = []
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for key, value in [("id", v) for v in _strings(self._config.get("post_ids"))] + [("slug", v) for v in _strings(self._config.get("slugs"))]:
                response = await client.post(self.api_url, json={"query": QUERY, "variables": {key: value, "first": max_comments}})
                if response.status_code >= 400:
                    continue
                post = (response.json().get("data") or {}).get("post") or {}
                for comment in _comments(post):
                    maker = bool(comment.get("maker") or (comment.get("user") or {}).get("isMaker"))
                    if maker and self._config.get("include_maker_replies") is False:
                        continue
                    signals.append(_signal(post, comment, maker))
                    if len(signals) >= limit:
                        return signals
        return signals


def _comments(post: dict[str, Any]) -> list[dict[str, Any]]:
    edges = ((post.get("comments") or {}).get("edges") or [])
    return [e.get("node") or e for e in edges if isinstance(e, dict)]


def _signal(post: dict[str, Any], comment: dict[str, Any], maker: bool) -> Signal:
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    slug = post.get("slug") or post.get("id")
    url = post.get("url") or f"https://www.producthunt.com/posts/{slug}"
    return Signal(
        id=_id("ph-comment", post.get("id") or slug, comment.get("id")),
        source_type=SignalSourceType.FORUM,
        source_adapter="product_hunt_launch_comments",
        title=f"{post.get('name') or slug} launch comment",
        content=str(comment.get("body") or "")[:500],
        url=url,
        author=user.get("username"),
        published_at=_parse_dt(comment.get("createdAt")),
        tags=["product-hunt", "launch-comment", "maker-reply" if maker else "user-comment"],
        credibility=min(max(float(comment.get("votesCount") or 0) / 50, 0.2), 1.0),
        metadata={
            "comment_id": comment.get("id"),
            "commenter_role": "maker" if maker else "community",
            "vote_count": comment.get("votesCount") or 0,
            "posted_at": comment.get("createdAt") or "",
            "launch_slug": slug,
            "product_tagline": post.get("tagline") or "",
            "source_url": url,
            "signal_role": "market",
        },
    )


def _strings(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    return [str(v).strip() for v in values if str(v).strip()]


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _id(*parts: object) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16]
