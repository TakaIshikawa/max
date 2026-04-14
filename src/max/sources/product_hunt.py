"""Product Hunt source adapter — devtools/AI product launches via GraphQL API."""

from __future__ import annotations

import logging
import os

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

PH_GRAPHQL = "https://api.producthunt.com/v2/api/graphql"

_DEFAULT_TOPICS = ["developer-tools", "artificial-intelligence"]

GRAPHQL_QUERY = """
query($topic: String!, $first: Int!) {
  topic(slug: $topic) {
    posts(first: $first, order: VOTES) {
      edges {
        node {
          id
          name
          tagline
          description
          url
          votesCount
          commentsCount
          createdAt
          makers {
            username
          }
          topics {
            edges {
              node {
                slug
                name
              }
            }
          }
        }
      }
    }
  }
}
"""


class ProductHuntAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "product_hunt"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def topics(self) -> list[str]:
        return self._config.get("topics", _DEFAULT_TOPICS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        token = os.environ.get("PRODUCT_HUNT_TOKEN")
        if not token:
            try:
                import subprocess
                result = subprocess.run(
                    ["vault", "get", "product_hunt/token"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    token = result.stdout.strip()
            except Exception:
                pass
        if not token:
            logger.warning("PRODUCT_HUNT_TOKEN not set — skipping Product Hunt adapter")
            return []

        signals: list[Signal] = []
        seen_ids: set[str] = set()
        topics = self.topics
        per_topic = max(limit // len(topics), 5)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for topic_slug in topics:
                if len(signals) >= limit:
                    break

                try:
                    resp = await fetch_with_retry(
                        PH_GRAPHQL,
                        client,
                        adapter_name=self.name,
                        method="POST",
                        json={
                            "query": GRAPHQL_QUERY,
                            "variables": {"topic": topic_slug, "first": per_topic},
                        },
                    )
                    data = resp.json()
                except AdapterFetchError:
                    logger.warning(
                        "Product Hunt query failed for topic: %s",
                        topic_slug,
                        exc_info=True,
                    )
                    continue

                posts = _extract_posts(data)
                for post in posts:
                    post_id = post.get("id", "")
                    if post_id in seen_ids:
                        continue
                    seen_ids.add(post_id)

                    if len(signals) >= limit:
                        break

                    votes = post.get("votesCount", 0)
                    comments = post.get("commentsCount", 0)
                    credibility = min(votes / 500, 1.0)

                    makers = [m.get("username", "") for m in post.get("makers", [])]
                    topics = _extract_topics(post)

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.TRENDING,
                            source_adapter=self.name,
                            title=post.get("name", ""),
                            content=(post.get("description") or post.get("tagline") or "")[:500],
                            url=post.get("url", ""),
                            published_at=_parse_dt(post.get("createdAt")),
                            tags=_build_tags(topics, post.get("tagline", "")),
                            credibility=credibility,
                            metadata={
                                "ph_id": post_id,
                                "votes": votes,
                                "comments": comments,
                                "topics": topics,
                                "makers": makers[:5],
                            },
                        )
                    )

        return signals[:limit]


def _extract_posts(data: dict) -> list[dict]:
    """Extract post nodes from GraphQL response."""
    try:
        edges = data["data"]["topic"]["posts"]["edges"]
        return [edge["node"] for edge in edges]
    except (KeyError, TypeError):
        return []


def _extract_topics(post: dict) -> list[str]:
    """Extract topic slugs from post."""
    try:
        edges = post.get("topics", {}).get("edges", [])
        return [edge["node"]["slug"] for edge in edges]
    except (KeyError, TypeError):
        return []


def _parse_dt(s: str | None):
    if not s:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_tags(topics: list[str], tagline: str) -> list[str]:
    """Build tags from PH topics and tagline keywords."""
    tags: set[str] = set()

    topic_map = {
        "developer-tools": "devtools",
        "artificial-intelligence": "ai",
        "machine-learning": "ml",
        "saas": "saas",
        "open-source": "open_source",
        "api": "api",
        "productivity": "productivity",
        "design-tools": "design",
        "no-code": "no-code",
        "analytics": "analytics",
    }

    for slug in topics:
        mapped = topic_map.get(slug)
        if mapped:
            tags.add(mapped)

    # Keyword scan on tagline
    lower = tagline.lower()
    keyword_tags = {
        "ai": ["ai", "artificial intelligence"],
        "agent": ["agent"],
        "llm": ["llm", "language model"],
        "mcp": ["mcp"],
        "devtools": ["developer", "devtool"],
        "api": ["api"],
    }
    for tag, keywords in keyword_tags.items():
        if any(kw in lower for kw in keywords):
            tags.add(tag)

    return sorted(tags)[:10]
