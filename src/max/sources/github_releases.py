"""GitHub releases source adapter -- release notes from configured repositories."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from urllib.parse import urlparse

import httpx

from max.sources.base import SourceAdapter
from max.sources.errors import (
    SourceAuthError,
    SourceParseError,
    SourceRateLimitError,
    SourceTransientError,
)
from max.sources.retry import with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

_DEFAULT_REPOSITORIES = [
    "modelcontextprotocol/servers",
    "langchain-ai/langchain",
    "openai/openai-python",
    "anthropics/anthropic-sdk-python",
    "vercel/ai",
]


class GitHubReleasesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "github_releases"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def repositories(self) -> list[str]:
        return self._config.get("repositories", _DEFAULT_REPOSITORIES)

    @property
    def include_drafts(self) -> bool:
        return bool(self._config.get("include_drafts", False))

    @property
    def include_prereleases(self) -> bool:
        return bool(self._config.get("include_prereleases", False))

    @property
    def token(self) -> str | None:
        configured = self._config.get("github_token") or self._config.get("token")
        return configured or os.environ.get("GITHUB_TOKEN")

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_releases")
    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        repo: str,
        *,
        page: int,
        per_page: int,
    ) -> tuple[list[dict], str | None]:
        """Fetch one GitHub releases page and return items plus the next URL."""
        try:
            resp = await client.get(
                f"{GITHUB_API}/repos/{repo}/releases",
                params={"per_page": per_page, "page": page},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429 or _is_github_rate_limit(e.response):
                retry_after = e.response.headers.get("Retry-After")
                retry_seconds = float(retry_after) if retry_after else None
                raise SourceRateLimitError(
                    f"Rate limit exceeded for releases: {repo}",
                    adapter_name=self.name,
                    retry_after=retry_seconds,
                ) from e
            if status in (401, 403):
                raise SourceAuthError(
                    f"Authentication failed (HTTP {status}) for releases: {repo}",
                    adapter_name=self.name,
                ) from e
            if 500 <= status < 600:
                raise SourceTransientError(
                    f"Server error (HTTP {status}) for releases: {repo}",
                    adapter_name=self.name,
                ) from e
            raise SourceTransientError(
                f"HTTP {status} for releases: {repo}",
                adapter_name=self.name,
            ) from e
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse releases response for: {repo}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, list):
            raise SourceParseError(
                f"Unexpected releases response for: {repo}",
                adapter_name=self.name,
            )

        return data, _next_link(resp.headers.get("Link", ""))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        repositories = self.repositories
        per_page = min(max(limit, 1), 100)

        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for repo in repositories:
                if len(signals) >= limit:
                    break

                page = 1
                next_url: str | None = None
                while len(signals) < limit:
                    try:
                        data, next_url = await self._fetch_page(
                            client,
                            repo,
                            page=page,
                            per_page=per_page,
                        )
                    except (SourceRateLimitError, SourceAuthError):
                        raise
                    except (
                        SourceTransientError,
                        SourceParseError,
                        httpx.RequestError,
                        httpx.TimeoutException,
                    ):
                        logger.warning(
                            "GitHub releases fetch failed for repo: %s",
                            repo,
                            exc_info=True,
                        )
                        break

                    if not data:
                        break

                    for release in data:
                        if len(signals) >= limit:
                            break
                        if release.get("draft") and not self.include_drafts:
                            continue
                        if release.get("prerelease") and not self.include_prereleases:
                            continue

                        html_url = release.get("html_url", "")
                        if not html_url or html_url in seen_urls:
                            continue
                        seen_urls.add(html_url)

                        title = _release_title(repo, release)
                        body = (release.get("body") or "").strip()

                        signals.append(
                            Signal(
                                source_type=SignalSourceType.ROADMAP,
                                source_adapter=self.name,
                                title=title,
                                content=body[:4000] if body else title,
                                url=html_url,
                                author=release.get("author", {}).get("login"),
                                published_at=_parse_dt(
                                    release.get("published_at") or release.get("created_at")
                                ),
                                tags=_build_tags(repo, release),
                                credibility=_credibility(release),
                                metadata={
                                    "github_release_id": release.get("id"),
                                    "repo": repo,
                                    "tag_name": release.get("tag_name"),
                                    "name": release.get("name"),
                                    "draft": bool(release.get("draft", False)),
                                    "prerelease": bool(release.get("prerelease", False)),
                                    "created_at": release.get("created_at"),
                                    "published_at": release.get("published_at"),
                                },
                            )
                        )

                    if not next_url:
                        break
                    page = _page_from_url(next_url) or page + 1

        return signals[:limit]


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _release_title(repo: str, release: dict) -> str:
    name = (release.get("name") or "").strip()
    tag = (release.get("tag_name") or "").strip()
    if name and tag and name != tag:
        return f"{repo} {name} ({tag})"
    if name or tag:
        return f"{repo} {name or tag}"
    return repo


def _build_tags(repo: str, release: dict) -> list[str]:
    tags: set[str] = {"github", "release"}
    text = " ".join(
        str(part or "")
        for part in [
            repo,
            release.get("name"),
            release.get("tag_name"),
            release.get("body"),
        ]
    ).lower()

    keyword_map = {
        "ai": ["ai", "artificial intelligence", "openai", "anthropic"],
        "agent": ["agent", "agentic"],
        "llm": ["llm", "language model", "gpt", "claude"],
        "mcp": ["mcp", "model context protocol"],
        "security": ["security", "vulnerability", "cve"],
        "typescript": ["typescript", "javascript", "vercel/ai"],
        "python": ["python"],
        "devtools": ["cli", "developer tool", "sdk"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)

    return sorted(tags)[:10]


def _credibility(release: dict) -> float:
    reactions = release.get("reactions") or {}
    total_reactions = reactions.get("total_count", 0) if isinstance(reactions, dict) else 0
    return min(0.4 + (total_reactions / 100), 1.0)


def _next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        start = section.find("<")
        end = section.find(">")
        if start != -1 and end > start:
            return section[start + 1:end]
    return None


def _page_from_url(url: str) -> int | None:
    try:
        parsed = urlparse(url)
        for piece in parsed.query.split("&"):
            key, _, value = piece.partition("=")
            if key == "page":
                return int(value)
    except ValueError:
        return None
    return None


def _is_github_rate_limit(response: httpx.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    return response.status_code == 403 and remaining == "0"
