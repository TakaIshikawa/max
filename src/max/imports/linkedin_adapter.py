"""LinkedIn source adapter — professional network signals, job postings, and industry trends."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"

_DEFAULT_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "developer tools",
    "devops",
    "cloud native",
    "open source",
]


class LinkedInAdapter(SourceAdapter):
    """Collects professional network signals from LinkedIn API.

    Fetches posts, job listings, and company updates to identify
    hiring trends and emerging skill requirements.
    """

    @property
    def name(self) -> str:
        return "linkedin"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def keywords(self) -> list[str]:
        return self._configured_terms("keywords", _DEFAULT_KEYWORDS)

    @property
    def _access_token(self) -> str | None:
        return self._config.get("access_token")

    @property
    def _api_base(self) -> str:
        return self._config.get("api_base", LINKEDIN_API_BASE)

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202304",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []

        posts_signals = await self._fetch_posts(limit=limit)
        signals.extend(posts_signals)

        remaining = limit - len(signals)
        if remaining > 0:
            job_signals = await self._fetch_jobs(limit=remaining)
            signals.extend(job_signals)

        return signals[:limit]

    async def _fetch_posts(self, *, limit: int = 15) -> list[Signal]:
        """Fetch posts/articles from LinkedIn based on keywords."""
        signals: list[Signal] = []
        per_keyword = max(limit // len(self.keywords), 3)

        async with httpx.AsyncClient(
            timeout=30,
            headers=self._auth_headers(),
            follow_redirects=True,
        ) as client:
            for keyword in self.keywords:
                if len(signals) >= limit:
                    break
                try:
                    resp = await fetch_with_retry(
                        f"{self._api_base}/posts",
                        client,
                        adapter_name=self.name,
                        params={"q": "search", "keywords": keyword, "count": per_keyword},
                    )
                    data = resp.json()
                except AdapterFetchError:
                    logger.warning(
                        "LinkedIn posts fetch failed for keyword=%s", keyword, exc_info=True,
                    )
                    continue
                except (ValueError, KeyError, TypeError):
                    logger.warning(
                        "LinkedIn posts parse failed for keyword=%s", keyword, exc_info=True,
                    )
                    continue

                for element in data.get("elements", []):
                    post_text = element.get("commentary", "") or element.get("text", "")
                    if not post_text:
                        continue

                    author_info = element.get("author", {})
                    author_name = (
                        author_info.get("name")
                        if isinstance(author_info, dict)
                        else str(author_info)
                    )

                    likes = _safe_int(element.get("likeCount", 0))
                    comments = _safe_int(element.get("commentCount", 0))
                    shares = _safe_int(element.get("shareCount", 0))
                    engagement = likes + comments * 2 + shares * 3

                    published_at = _parse_timestamp(element.get("publishedAt"))

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.MARKET,
                            source_adapter=self.name,
                            title=post_text[:120],
                            content=post_text[:1000],
                            url=element.get("url", f"https://www.linkedin.com/feed/update/{element.get('id', '')}"),
                            author=author_name,
                            published_at=published_at,
                            tags=_extract_tags(post_text, keyword),
                            credibility=min(engagement / 500, 1.0),
                            metadata={
                                "post_id": element.get("id"),
                                "search_keyword": keyword,
                                "like_count": likes,
                                "comment_count": comments,
                                "share_count": shares,
                                "engagement_score": engagement,
                                "content_type": "post",
                            },
                        )
                    )

        return signals[:limit]

    async def _fetch_jobs(self, *, limit: int = 15) -> list[Signal]:
        """Fetch job listings to identify hiring trends and skill demand."""
        signals: list[Signal] = []
        per_keyword = max(limit // len(self.keywords), 3)

        async with httpx.AsyncClient(
            timeout=30,
            headers=self._auth_headers(),
            follow_redirects=True,
        ) as client:
            for keyword in self.keywords:
                if len(signals) >= limit:
                    break
                try:
                    resp = await fetch_with_retry(
                        f"{self._api_base}/jobSearch",
                        client,
                        adapter_name=self.name,
                        params={"keywords": keyword, "count": per_keyword},
                    )
                    data = resp.json()
                except AdapterFetchError:
                    logger.warning(
                        "LinkedIn jobs fetch failed for keyword=%s", keyword, exc_info=True,
                    )
                    continue
                except (ValueError, KeyError, TypeError):
                    logger.warning(
                        "LinkedIn jobs parse failed for keyword=%s", keyword, exc_info=True,
                    )
                    continue

                for element in data.get("elements", []):
                    title = element.get("title", "")
                    if not title:
                        continue

                    description = element.get("description", "")
                    company = element.get("company", {})
                    company_name = (
                        company.get("name", "")
                        if isinstance(company, dict)
                        else str(company)
                    )
                    location = element.get("location", "")
                    skills = element.get("skills", [])
                    posted_at = _parse_timestamp(element.get("postedAt"))

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.MARKET,
                            source_adapter=self.name,
                            title=f"[Job] {title} at {company_name}" if company_name else f"[Job] {title}",
                            content=description[:1000] if description else title,
                            url=element.get("url", f"https://www.linkedin.com/jobs/view/{element.get('id', '')}"),
                            author=company_name or None,
                            published_at=posted_at,
                            tags=_extract_tags(f"{title} {description}", keyword),
                            credibility=0.7,
                            metadata={
                                "job_id": element.get("id"),
                                "search_keyword": keyword,
                                "company": company_name,
                                "location": location,
                                "skills": skills if isinstance(skills, list) else [],
                                "content_type": "job",
                            },
                        )
                    )

        return signals[:limit]


def _safe_int(value: object) -> int:
    """Safely convert a value to int."""
    if isinstance(value, int):
        return value
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _parse_timestamp(value: object) -> datetime | None:
    """Parse a LinkedIn timestamp (epoch ms or ISO string)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _extract_tags(text: str, keyword: str) -> list[str]:
    """Extract tags from text and search keyword."""
    tags: list[str] = ["linkedin"]
    lower = text.lower()

    keyword_tag = keyword.lower().replace(" ", "-")
    if keyword_tag not in tags:
        tags.append(keyword_tag)

    tech_keywords = {
        "ai": ["ai", "artificial intelligence", "llm", "gpt", "machine learning"],
        "cloud": ["cloud", "aws", "azure", "gcp", "kubernetes"],
        "devops": ["devops", "ci/cd", "infrastructure", "sre"],
        "security": ["security", "cybersecurity", "devsecops"],
        "data": ["data engineering", "data science", "analytics"],
        "frontend": ["react", "vue", "angular", "frontend"],
        "backend": ["backend", "microservices", "api"],
        "mobile": ["mobile", "ios", "android", "react native"],
    }
    for tag, terms in tech_keywords.items():
        if any(t in lower for t in terms) and tag not in tags:
            tags.append(tag)

    return tags
