"""LinkedIn source adapter — professional network signals and hiring trends."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"
_DEFAULT_ACCESS_TOKEN_ENV = "LINKEDIN_ACCESS_TOKEN"

_DEFAULT_KEYWORDS = [
    "developer tools",
    "AI engineering",
    "open source",
    "LLM",
]

_KEYWORD_TAGS = {
    "ai": ["ai", "llm", "gpt", "claude", "openai", "anthropic", "machine learning"],
    "agent": ["agent", "agentic", "autonomous"],
    "mcp": ["mcp", "model context protocol"],
    "hiring": ["hiring", "job", "career", "role", "position"],
    "devtools": ["devtools", "developer tools", "tooling", "sdk"],
    "open_source": ["open source", "oss", "foss"],
    "startup": ["startup", "seed", "series a", "funding"],
}


class LinkedInAdapter(SourceAdapter):
    """Fetch posts and job listings from LinkedIn API for professional insights."""

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
    def access_token_env(self) -> str:
        value = self._config.get("access_token_env", _DEFAULT_ACCESS_TOKEN_ENV)
        return value if isinstance(value, str) and value.strip() else _DEFAULT_ACCESS_TOKEN_ENV

    @property
    def organization_ids(self) -> list[str]:
        return _normalize_ids(self._config.get("organization_ids", []))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        token = os.environ.get(self.access_token_env)
        if not token:
            logger.warning("LinkedIn access token not found in env var %s", self.access_token_env)
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "max-linkedin-adapter/0.1",
            "Accept": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        signals: list[Signal] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(
            timeout=30, headers=headers, follow_redirects=True,
        ) as client:
            # Fetch posts from organizations
            for org_id in self.organization_ids:
                if len(signals) >= limit:
                    break
                await self._fetch_org_posts(
                    client, org_id=org_id, signals=signals,
                    seen_ids=seen_ids, limit=limit,
                )

            # Fetch job postings by keywords
            for keyword in self.keywords:
                if len(signals) >= limit:
                    break
                await self._fetch_jobs(
                    client, keyword=keyword, signals=signals,
                    seen_ids=seen_ids, limit=limit,
                )

        return signals[:limit]

    async def _fetch_org_posts(
        self,
        client: httpx.AsyncClient,
        *,
        org_id: str,
        signals: list[Signal],
        seen_ids: set[str],
        limit: int,
    ) -> None:
        per_org = min(max(limit - len(signals), 5), 50)
        try:
            resp = await fetch_with_retry(
                f"{LINKEDIN_API_BASE}/organizationPosts",
                client,
                adapter_name=self.name,
                params={"q": "organization", "organization": org_id, "count": per_org},
            )
            data = resp.json()
        except (AdapterFetchError, httpx.RequestError, httpx.TimeoutException, ValueError):
            logger.warning("LinkedIn org posts fetch failed for %s", org_id, exc_info=True)
            return

        elements = data.get("elements", [])
        if not isinstance(elements, list):
            return

        for post in elements:
            if len(signals) >= limit:
                break
            if not isinstance(post, dict):
                continue
            post_id = post.get("id")
            if not post_id or str(post_id) in seen_ids:
                continue
            signal = self._post_to_signal(post, org_id=org_id)
            if signal is None:
                continue
            seen_ids.add(str(post_id))
            signals.append(signal)

    async def _fetch_jobs(
        self,
        client: httpx.AsyncClient,
        *,
        keyword: str,
        signals: list[Signal],
        seen_ids: set[str],
        limit: int,
    ) -> None:
        per_kw = min(max(limit - len(signals), 5), 25)
        try:
            resp = await fetch_with_retry(
                f"{LINKEDIN_API_BASE}/jobSearch",
                client,
                adapter_name=self.name,
                params={"keywords": keyword, "count": per_kw},
            )
            data = resp.json()
        except (AdapterFetchError, httpx.RequestError, httpx.TimeoutException, ValueError):
            logger.warning("LinkedIn job search failed for: %s", keyword, exc_info=True)
            return

        elements = data.get("elements", [])
        if not isinstance(elements, list):
            return

        for job in elements:
            if len(signals) >= limit:
                break
            if not isinstance(job, dict):
                continue
            job_id = job.get("id")
            if not job_id or str(job_id) in seen_ids:
                continue
            signal = self._job_to_signal(job, keyword=keyword)
            if signal is None:
                continue
            seen_ids.add(str(job_id))
            signals.append(signal)

    def _post_to_signal(self, post: dict, *, org_id: str) -> Signal | None:
        text = _extract_post_text(post)
        if not text:
            return None

        post_id = str(post.get("id", ""))
        likes = _int_or_zero(post.get("likeCount"))
        comments = _int_or_zero(post.get("commentCount"))
        timestamp = _parse_timestamp(post.get("createdAt"))

        return Signal(
            source_type=SignalSourceType.MARKET,
            source_adapter=self.name,
            title=_title_from_text(text),
            content=text[:1000],
            url=f"https://www.linkedin.com/feed/update/{post_id}",
            author=org_id,
            published_at=timestamp,
            tags=_extract_tags(text),
            credibility=_credibility(likes=likes, comments=comments),
            metadata={
                "post_id": post_id,
                "organization_id": org_id,
                "likes": likes,
                "comments": comments,
                "type": "post",
            },
        )

    def _job_to_signal(self, job: dict, *, keyword: str) -> Signal | None:
        title = job.get("title", "")
        if not title:
            return None

        job_id = str(job.get("id", ""))
        company = job.get("companyName", "")
        location = job.get("location", "")
        description = job.get("description", "")
        skills = _extract_skills(job)

        return Signal(
            source_type=SignalSourceType.MARKET,
            source_adapter=self.name,
            title=f"{title} at {company}" if company else title,
            content=description[:1000] if description else title,
            url=f"https://www.linkedin.com/jobs/view/{job_id}",
            author=company or None,
            published_at=_parse_timestamp(job.get("listedAt")),
            tags=_extract_tags(f"{title} {description}", extra=["hiring"]),
            credibility=0.5,
            metadata={
                "job_id": job_id,
                "company": company,
                "location": location,
                "skills": skills,
                "keyword": keyword,
                "type": "job",
            },
        )


def _normalize_ids(values: object) -> list[str]:
    if not isinstance(values, list):
        values = [values]
    result: list[str] = []
    seen: set[str] = set()
    for v in values:
        if not isinstance(v, (str, int)) or isinstance(v, bool):
            continue
        s = str(v).strip()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _int_or_zero(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    # LinkedIn uses epoch milliseconds
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        except (OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _extract_post_text(post: dict) -> str:
    text = post.get("commentary", "")
    if not text:
        text = post.get("text", "")
    return text if isinstance(text, str) else ""


def _extract_skills(job: dict) -> list[str]:
    skills = job.get("skills", [])
    if not isinstance(skills, list):
        return []
    return [str(s) for s in skills if isinstance(s, str)][:10]


def _title_from_text(text: str) -> str:
    line = " ".join(text.split())
    return line[:117] + "..." if len(line) > 120 else line


def _extract_tags(text: str, extra: list[str] | None = None) -> list[str]:
    tags: set[str] = {"linkedin"}
    lower = text.lower()

    for tag, keywords in _KEYWORD_TAGS.items():
        if any(kw in lower for kw in keywords):
            tags.add(tag)

    if extra:
        tags.update(extra)

    return sorted(tags)[:10]


def _credibility(*, likes: int, comments: int) -> float:
    score = (likes * 1) + (comments * 3)
    return min(0.3 + (score / 200.0), 1.0)
