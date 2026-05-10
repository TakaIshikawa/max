"""LinkedIn source adapter — professional insights, job postings, and industry trends."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

LINKEDIN_API = "https://api.linkedin.com/v2"

_DEFAULT_ACCESS_TOKEN_ENV = "LINKEDIN_ACCESS_TOKEN"

_DEFAULT_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "developer tools",
    "open source",
    "python",
    "typescript",
]

_KEYWORD_TAGS: dict[str, str] = {
    "ai": "ai",
    "artificial intelligence": "ai",
    "machine learning": "ml",
    "llm": "llm",
    "mcp": "mcp",
    "agent": "agent",
    "devops": "devops",
    "cloud": "cloud",
    "security": "security",
    "python": "python",
    "typescript": "typescript",
    "rust": "rust",
    "golang": "golang",
    "open source": "open-source",
}


def _extract_tags(text: str, keyword: str) -> list[str]:
    """Build signal tags from post text and search keyword."""
    tags: set[str] = {"linkedin"}

    keyword_tag = keyword.strip().lower().replace(" ", "-")[:30]
    if keyword_tag:
        tags.add(keyword_tag)

    text_lower = text.lower()
    for term, tag in _KEYWORD_TAGS.items():
        if term in text_lower:
            tags.add(tag)

    return sorted(tags)[:10]


def _parse_timestamp(ts: int | None) -> datetime | None:
    """Parse LinkedIn epoch millisecond timestamp."""
    if ts is None or not isinstance(ts, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    except (OSError, ValueError, OverflowError):
        return None


def _title_from_text(text: str) -> str:
    """Create a title from post text."""
    title = " ".join(text.split())
    if len(title) <= 100:
        return title
    return f"{title[:97].rstrip()}..."


def _engagement_credibility(likes: int, comments: int, shares: int) -> float:
    """Compute credibility score from engagement metrics."""
    engagement = likes + (comments * 2) + (shares * 3)
    return min(round(0.1 + (engagement / 200), 3), 1.0)


def _extract_skills_from_job(job: dict) -> list[str]:
    """Extract skill requirements from a job posting."""
    skills: list[str] = []
    description = job.get("description", {})
    if isinstance(description, dict):
        text = description.get("text", "")
    elif isinstance(description, str):
        text = description
    else:
        text = ""

    skill_keywords = [
        "python", "typescript", "javascript", "rust", "golang", "java",
        "kubernetes", "docker", "aws", "gcp", "azure", "terraform",
        "react", "node", "django", "fastapi", "flask",
    ]
    text_lower = text.lower()
    for skill in skill_keywords:
        if skill in text_lower:
            skills.append(skill)

    return skills[:10]


class LinkedInAdapter(SourceAdapter):
    """Fetch posts, job listings, and company updates from LinkedIn API."""

    @property
    def name(self) -> str:
        return "linkedin"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def keywords(self) -> list[str]:
        return self._configured_terms("keywords", _DEFAULT_KEYWORDS)

    @property
    def access_token_env(self) -> str:
        return self._config.get("access_token_env", _DEFAULT_ACCESS_TOKEN_ENV)

    @property
    def include_jobs(self) -> bool:
        return bool(self._config.get("include_jobs", True))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        access_token = os.environ.get(self.access_token_env, "")
        if not access_token:
            logger.warning(
                "%s: no access token found in env var %s",
                self.name, self.access_token_env,
            )
            return []

        signals: list[Signal] = []
        seen_ids: set[str] = set()
        keywords = self.keywords

        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "max-linkedin-adapter/0.1",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for keyword in keywords:
                if len(signals) >= limit:
                    break

                posts = await self._search_posts(client, keyword=keyword)
                if posts:
                    for post in posts:
                        if len(signals) >= limit:
                            break
                        signal = self._post_to_signal(post, keyword, seen_ids)
                        if signal:
                            signals.append(signal)

                if self.include_jobs and len(signals) < limit:
                    jobs = await self._search_jobs(client, keyword=keyword)
                    if jobs:
                        for job in jobs:
                            if len(signals) >= limit:
                                break
                            signal = self._job_to_signal(job, keyword, seen_ids)
                            if signal:
                                signals.append(signal)

        return signals[:limit]

    def _post_to_signal(
        self, post: dict, keyword: str, seen_ids: set[str],
    ) -> Signal | None:
        """Convert a LinkedIn post to a Signal."""
        post_id = post.get("id")
        if not post_id:
            return None
        post_id = str(post_id)
        if post_id in seen_ids:
            return None
        seen_ids.add(post_id)

        text = ""
        commentary = post.get("commentary", {})
        if isinstance(commentary, dict):
            text = commentary.get("text", "")
        elif isinstance(commentary, str):
            text = commentary

        if not text:
            text = post.get("text", "")

        likes = post.get("likeCount", 0) if isinstance(post.get("likeCount"), int) else 0
        comments = post.get("commentCount", 0) if isinstance(post.get("commentCount"), int) else 0
        shares = post.get("shareCount", 0) if isinstance(post.get("shareCount"), int) else 0

        author_name = None
        author_data = post.get("author", {})
        if isinstance(author_data, dict):
            author_name = author_data.get("name")
        elif isinstance(author_data, str):
            author_name = author_data

        return Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter=self.name,
            title=_title_from_text(text) if text else "LinkedIn Post",
            content=text[:500] if text else "",
            url=f"https://www.linkedin.com/feed/update/{post_id}",
            author=author_name,
            published_at=_parse_timestamp(post.get("created", {}).get("time"))
            if isinstance(post.get("created"), dict) else None,
            tags=_extract_tags(text, keyword),
            credibility=_engagement_credibility(likes, comments, shares),
            metadata={
                "post_id": post_id,
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "search_keyword": keyword,
            },
        )

    def _job_to_signal(
        self, job: dict, keyword: str, seen_ids: set[str],
    ) -> Signal | None:
        """Convert a LinkedIn job posting to a Signal."""
        job_id = job.get("id")
        if not job_id:
            return None
        job_id = str(job_id)
        dedup_key = f"job-{job_id}"
        if dedup_key in seen_ids:
            return None
        seen_ids.add(dedup_key)

        title = job.get("title", "")
        company = job.get("companyName", "")
        location = job.get("location", "")

        description = job.get("description", {})
        if isinstance(description, dict):
            desc_text = description.get("text", "")
        elif isinstance(description, str):
            desc_text = description
        else:
            desc_text = ""

        skills = _extract_skills_from_job(job)

        return Signal(
            source_type=SignalSourceType.MARKET,
            source_adapter=self.name,
            title=f"{title} at {company}" if company else title,
            content=desc_text[:500] if desc_text else title,
            url=f"https://www.linkedin.com/jobs/view/{job_id}",
            author=company or None,
            published_at=_parse_timestamp(job.get("listedAt")),
            tags=_extract_tags(desc_text or title, keyword),
            credibility=0.7,
            metadata={
                "job_id": job_id,
                "company": company,
                "location": location,
                "skills": skills,
                "search_keyword": keyword,
            },
        )

    async def _search_posts(
        self,
        client: httpx.AsyncClient,
        *,
        keyword: str,
    ) -> list[dict] | None:
        """Search LinkedIn posts by keyword."""
        try:
            resp = await fetch_with_retry(
                f"{LINKEDIN_API}/search/posts",
                client,
                adapter_name=self.name,
                params={"q": "search", "keywords": keyword, "count": 10},
            )
            data = resp.json()
        except Exception:
            logger.warning(
                "%s: failed to search posts for keyword '%s'",
                self.name, keyword, exc_info=True,
            )
            return None

        if not isinstance(data, dict):
            return None

        elements = data.get("elements")
        if not isinstance(elements, list):
            return None
        return [e for e in elements if isinstance(e, dict)]

    async def _search_jobs(
        self,
        client: httpx.AsyncClient,
        *,
        keyword: str,
    ) -> list[dict] | None:
        """Search LinkedIn job listings by keyword."""
        try:
            resp = await fetch_with_retry(
                f"{LINKEDIN_API}/jobSearch",
                client,
                adapter_name=self.name,
                params={"keywords": keyword, "count": 5},
            )
            data = resp.json()
        except Exception:
            logger.warning(
                "%s: failed to search jobs for keyword '%s'",
                self.name, keyword, exc_info=True,
            )
            return None

        if not isinstance(data, dict):
            return None

        elements = data.get("elements")
        if not isinstance(elements, list):
            return None
        return [e for e in elements if isinstance(e, dict)]
