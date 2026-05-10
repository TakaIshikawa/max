"""Product Hunt source adapter for launch signals.

Collects product launch signals via the Product Hunt GraphQL API.  Fetches
daily top products, upcoming launches, and collection data.  Extracts upvotes,
comments, maker profiles, and product categories to identify emerging tools
and SaaS trends.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

PH_API = "https://api.producthunt.com/v2/api/graphql"

_DEFAULT_TOPICS = ["developer-tools", "artificial-intelligence", "saas", "productivity"]

_POSTS_QUERY = """\
query($postedAfter: DateTime, $topic: String, $first: Int, $after: String) {
  posts(postedAfter: $postedAfter, topic: $topic, first: $first, after: $after, order: VOTES) {
    edges {
      node {
        id
        name
        tagline
        url
        votesCount
        commentsCount
        createdAt
        featuredAt
        website
        topics {
          edges {
            node {
              name
              slug
            }
          }
        }
        makers {
          id
          name
          username
        }
        thumbnail {
          url
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


def _get_token() -> str | None:
    """Resolve Product Hunt API token from env or vault."""
    token = os.environ.get("PRODUCTHUNT_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["vault", "get", "producthunt/token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _parse_dt(s: str | None) -> datetime | None:
    """Parse ISO 8601 datetime from Product Hunt API responses."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _extract_topics(topic_edges: list[dict]) -> list[str]:
    """Extract topic slugs from GraphQL topic edges."""
    topics: list[str] = []
    for edge in topic_edges:
        node = edge.get("node", {})
        slug = node.get("slug", "")
        if slug:
            topics.append(slug)
    return topics


def _build_tags(topic_slugs: list[str], search_topic: str) -> list[str]:
    """Build normalized tags from product topics and search context."""
    tags: set[str] = set()
    topic_map = {
        "developer-tools": "devtools",
        "artificial-intelligence": "ai",
        "saas": "saas",
        "productivity": "productivity",
        "design-tools": "design",
        "marketing": "marketing",
        "fintech": "fintech",
        "open-source": "open-source",
        "no-code": "no-code",
        "api": "api",
        "analytics": "analytics",
        "automation": "automation",
    }
    for slug in topic_slugs:
        mapped = topic_map.get(slug)
        if mapped:
            tags.add(mapped)
        else:
            tags.add(slug)

    search_tag = topic_map.get(search_topic, search_topic)
    if search_tag:
        tags.add(search_tag)

    tags.add("producthunt")
    return sorted(tags)[:10]


class ProductHuntAdapter(SourceAdapter):
    """Fetches daily top products and upcoming launches by topic.

    Extracts upvotes, comments, maker info, and categories.
    Handles OAuth token authentication and API pagination via ``fetch_with_retry``.
    """

    @property
    def name(self) -> str:
        return "producthunt_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKETPLACE.value

    @property
    def topics(self) -> list[str]:
        return self._configured_terms("topics", _DEFAULT_TOPICS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        token = _get_token()

        if not token:
            logger.warning("No Product Hunt API token configured")
            return signals

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        per_topic = max(limit // max(len(self.topics), 1), 3)

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for topic in self.topics:
                if len(signals) >= limit:
                    break

                cursor: str | None = None

                while len(signals) < limit:
                    variables: dict = {
                        "topic": topic,
                        "first": min(per_topic, 20),
                    }
                    if cursor:
                        variables["after"] = cursor

                    try:
                        resp = await fetch_with_retry(
                            PH_API,
                            client,
                            adapter_name=self.name,
                            method="POST",
                            json={"query": _POSTS_QUERY, "variables": variables},
                        )
                        data = resp.json()
                    except Exception:
                        logger.warning(
                            "Product Hunt fetch failed for topic: %s",
                            topic,
                            exc_info=True,
                        )
                        break

                    posts_data = (data.get("data") or {}).get("posts", {})
                    edges = posts_data.get("edges", [])
                    page_info = posts_data.get("pageInfo", {})

                    for edge in edges:
                        node = edge.get("node", {})
                        post_id = str(node.get("id", ""))
                        if not post_id or post_id in seen:
                            continue
                        seen.add(post_id)

                        votes = node.get("votesCount", 0)
                        topic_edges = (node.get("topics") or {}).get("edges", [])
                        topic_slugs = _extract_topics(topic_edges)
                        makers = node.get("makers", []) or []

                        signals.append(
                            Signal(
                                source_type=SignalSourceType.MARKETPLACE,
                                source_adapter=self.name,
                                title=node.get("name", ""),
                                content=(node.get("tagline") or "")[:500],
                                url=node.get("url", ""),
                                author=makers[0].get("name") if makers else None,
                                published_at=_parse_dt(node.get("createdAt")),
                                tags=_build_tags(topic_slugs, topic),
                                credibility=min(votes / 1000, 1.0),
                                metadata={
                                    "post_id": post_id,
                                    "votes": votes,
                                    "comments": node.get("commentsCount", 0),
                                    "topics": topic_slugs[:10],
                                    "makers": [
                                        {"name": m.get("name"), "username": m.get("username")}
                                        for m in makers[:5]
                                    ],
                                    "featured_at": node.get("featuredAt"),
                                    "website": node.get("website"),
                                    "thumbnail": (node.get("thumbnail") or {}).get("url"),
                                },
                            )
                        )

                        if len(signals) >= limit:
                            break

                    if not page_info.get("hasNextPage") or len(signals) >= limit:
                        break
                    cursor = page_info.get("endCursor")

        return signals[:limit]
