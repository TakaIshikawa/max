"""Indie Hackers source adapter for bootstrapped startup signals.

Collects signals from bootstrapped startup discussions and revenue milestones
via the Indie Hackers website.  Fetches product posts, revenue updates, and
community discussions.  Extracts MRR milestones, tech stack mentions, and
growth strategies from the indie maker community.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

INDIEHACKERS_API = "https://www.indiehackers.com/api"

_DEFAULT_CATEGORIES = ["products", "milestones", "discussions"]
_DEFAULT_SEARCH_TERMS = ["saas", "bootstrapped", "mrr", "launch", "revenue"]

_TECH_STACK_PATTERNS = [
    "react", "vue", "svelte", "nextjs", "next.js", "nuxt", "remix",
    "tailwind", "typescript", "python", "django", "flask", "fastapi",
    "ruby", "rails", "laravel", "php", "golang", "go", "rust",
    "node", "express", "postgres", "mongodb", "redis", "supabase",
    "firebase", "aws", "vercel", "stripe", "paddle",
]

_MRR_PATTERN = re.compile(
    r"\$[\d,]+(?:\.\d{2})?\s*(?:/mo|mrr|arr|monthly|per\s*month)",
    re.IGNORECASE,
)

_REVENUE_PATTERN = re.compile(
    r"\$[\d,]+(?:\.\d{2})?(?:k|K)?\s*(?:mrr|arr|revenue|/mo)",
    re.IGNORECASE,
)


def _parse_dt(s: str | None) -> datetime | None:
    """Parse ISO 8601 datetime from Indie Hackers API responses."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _extract_tech_stack(text: str) -> list[str]:
    """Extract technology mentions from post content."""
    if not text:
        return []
    lower = text.lower()
    return sorted({t for t in _TECH_STACK_PATTERNS if t in lower})


def _extract_revenue(text: str) -> str | None:
    """Extract revenue/MRR mentions from text."""
    if not text:
        return None
    match = _MRR_PATTERN.search(text) or _REVENUE_PATTERN.search(text)
    return match.group(0) if match else None


def _build_tags(post: dict, category: str) -> list[str]:
    """Build tags for an Indie Hackers signal."""
    tags: set[str] = {"indiehackers", "bootstrapped"}
    if category:
        tags.add(category)

    text = f"{post.get('title', '')} {post.get('body', '')}".lower()

    if any(kw in text for kw in ("mrr", "revenue", "arr", "income")):
        tags.add("revenue")
    if any(kw in text for kw in ("launch", "launched", "ship", "shipped")):
        tags.add("launch")
    if any(kw in text for kw in ("growth", "scale", "marketing", "seo")):
        tags.add("growth")
    if any(kw in text for kw in ("tech stack", "built with", "using")):
        tags.add("techstack")

    return sorted(tags)


def _compute_credibility(post: dict) -> float:
    """Compute credibility score based on engagement metrics."""
    upvotes = post.get("upvotes", 0)
    comments = post.get("comment_count", 0)
    score = min((upvotes + comments * 2) / 200, 1.0)
    return max(score, 0.1)


class IndieHackersAdapter(SourceAdapter):
    """Fetches product listings and milestone posts from Indie Hackers.

    Extracts revenue data, tech stack mentions, and growth tactics from
    bootstrapped startup discussions.

    Config options:
        categories: list of content categories to fetch (default: products, milestones, discussions)
        search_terms: list of search terms for filtering posts
        query: single search query string
    """

    @property
    def name(self) -> str:
        return "indiehackers_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    @property
    def search_terms(self) -> list[str]:
        return self._configured_terms("search_terms", _DEFAULT_SEARCH_TERMS)

    @property
    def query(self) -> str | None:
        q = self._config.get("query")
        return q if isinstance(q, str) else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            if self.query:
                signals = await self._search_posts(client, self.query, seen, limit)
            else:
                for term in self.search_terms:
                    if len(signals) >= limit:
                        break
                    new_signals = await self._search_posts(
                        client, term, seen, limit - len(signals),
                    )
                    signals.extend(new_signals)

        return signals[:limit]

    async def _search_posts(
        self,
        client: httpx.AsyncClient,
        query: str,
        seen: set[str],
        limit: int,
    ) -> list[Signal]:
        """Search Indie Hackers for posts matching a query."""
        signals: list[Signal] = []

        try:
            resp = await fetch_with_retry(
                f"{INDIEHACKERS_API}/posts",
                client,
                adapter_name=self.name,
                params={
                    "q": query,
                    "page_size": min(limit, 25),
                },
            )
            data = resp.json()
        except Exception:
            logger.warning("Indie Hackers search failed for: %s", query, exc_info=True)
            return signals

        for post in data.get("posts", []):
            post_id = post.get("id", "")
            if not post_id or post_id in seen:
                continue
            seen.add(post_id)

            title = post.get("title", "")
            body = post.get("body", "")
            author = post.get("author", {}).get("username", "")
            category = post.get("category", "")
            full_text = f"{title} {body}"

            tech_stack = _extract_tech_stack(full_text)
            revenue_mention = _extract_revenue(full_text)

            signals.append(
                Signal(
                    source_type=SignalSourceType.FORUM,
                    source_adapter=self.name,
                    title=title or post_id,
                    content=(body or title)[:500],
                    url=post.get("url", f"https://www.indiehackers.com/post/{post_id}"),
                    author=author or None,
                    published_at=_parse_dt(post.get("published_at")),
                    tags=_build_tags(post, category),
                    credibility=_compute_credibility(post),
                    metadata={
                        "post_id": post_id,
                        "category": category,
                        "upvotes": post.get("upvotes", 0),
                        "comment_count": post.get("comment_count", 0),
                        "tech_stack": tech_stack,
                        "revenue_mention": revenue_mention,
                        "product_name": post.get("product", {}).get("name"),
                        "product_tagline": post.get("product", {}).get("tagline"),
                    },
                )
            )

            if len(signals) >= limit:
                break

        return signals
