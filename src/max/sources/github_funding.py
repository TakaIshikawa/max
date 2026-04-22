"""GitHub funding source adapter -- sponsorship links from configured repositories."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

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

_SUPPORTED_PLATFORMS = {
    "custom",
    "github sponsors",
    "ko-fi",
    "kofi",
    "open collective",
    "patreon",
    "sponsorship",
}


@dataclass(frozen=True)
class FundingLink:
    """Normalized repository funding link."""

    platform: str
    url: str


class GitHubFundingAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "github_funding"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FUNDING.value

    @property
    def repositories(self) -> list[str]:
        return self._config.get("repositories", _DEFAULT_REPOSITORIES)

    @property
    def token(self) -> str | None:
        configured = self._config.get("github_token") or self._config.get("token")
        return configured or os.environ.get("GITHUB_TOKEN")

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_funding")
    async def _fetch_profile(self, client: httpx.AsyncClient, repo: str) -> dict:
        """Fetch community profile data for a repository."""
        try:
            resp = await client.get(f"{GITHUB_API}/repos/{repo}/community/profile")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429 or _is_github_rate_limit(e.response):
                retry_after = e.response.headers.get("Retry-After")
                retry_seconds = float(retry_after) if retry_after else None
                raise SourceRateLimitError(
                    f"Rate limit exceeded for funding profile: {repo}",
                    adapter_name=self.name,
                    retry_after=retry_seconds,
                ) from e
            if status in (401, 403):
                raise SourceAuthError(
                    f"Authentication failed (HTTP {status}) for funding profile: {repo}",
                    adapter_name=self.name,
                ) from e
            if 500 <= status < 600:
                raise SourceTransientError(
                    f"Server error (HTTP {status}) for funding profile: {repo}",
                    adapter_name=self.name,
                ) from e
            raise SourceTransientError(
                f"HTTP {status} for funding profile: {repo}",
                adapter_name=self.name,
            ) from e
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse funding profile response for: {repo}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, dict):
            raise SourceParseError(
                f"Unexpected funding profile response for: {repo}",
                adapter_name=self.name,
            )
        return data

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()

        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for repo in self.repositories:
                if len(signals) >= limit:
                    break

                repo = repo.strip()
                if not repo:
                    continue

                try:
                    profile = await self._fetch_profile(client, repo)
                except (SourceRateLimitError, SourceAuthError):
                    raise
                except (
                    SourceTransientError,
                    SourceParseError,
                    httpx.RequestError,
                    httpx.TimeoutException,
                ):
                    logger.warning(
                        "GitHub funding fetch failed for repo: %s",
                        repo,
                        exc_info=True,
                    )
                    continue

                evidence_url = _evidence_url(repo, profile)
                for link in _funding_links(profile):
                    if len(signals) >= limit:
                        break
                    if link.url in seen_urls:
                        continue
                    seen_urls.add(link.url)

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.FUNDING,
                            source_adapter=self.name,
                            title=f"{repo} accepts funding via {link.platform}",
                            content=_content(repo, link),
                            url=link.url,
                            author=repo.split("/", 1)[0],
                            tags=_build_tags(link.platform),
                            credibility=0.7,
                            metadata={
                                "repo": repo,
                                "repository": repo,
                                "funding_platform": link.platform,
                                "funding_url": link.url,
                                "evidence_url": evidence_url,
                                "signal_role": "market",
                                "role_hint": "market",
                            },
                        )
                    )

        return signals[:limit]


def _funding_links(profile: dict) -> list[FundingLink]:
    """Return supported funding links from a GitHub community profile response."""
    raw_links = profile.get("funding_links") or []
    if not isinstance(raw_links, list):
        return []

    links: list[FundingLink] = []
    for item in raw_links:
        if not isinstance(item, dict):
            continue

        platform = str(item.get("platform") or "").strip()
        url = str(item.get("url") or "").strip()
        if not platform or not url:
            continue
        if _platform_key(platform) not in _SUPPORTED_PLATFORMS:
            continue

        links.append(FundingLink(platform=platform, url=url))

    return links


def _evidence_url(repo: str, profile: dict) -> str:
    """Return the funding file URL if GitHub exposes it, else the repo funding page."""
    files = profile.get("files")
    if isinstance(files, dict):
        funding = files.get("funding")
        if isinstance(funding, dict):
            html_url = funding.get("html_url")
            if isinstance(html_url, str) and html_url.strip():
                return html_url.strip()

    return f"https://github.com/{repo}/community"


def _build_tags(platform: str) -> list[str]:
    tags = {"github", "funding", "sponsorship"}
    platform_key = _platform_key(platform).replace(" ", "-")
    if platform_key:
        tags.add(platform_key)
    return sorted(tags)[:10]


def _content(repo: str, link: FundingLink) -> str:
    return (
        f"{repo} exposes a funding link for {link.platform}. "
        "Maintainer sponsorship can indicate active ecosystem demand and sustainability needs."
    )


def _platform_key(platform: str) -> str:
    return platform.strip().lower()


def _is_github_rate_limit(response: httpx.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    message = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            message = str(payload.get("message", "")).lower()
    except ValueError:
        pass
    return response.status_code == 403 and (
        remaining == "0" or "rate limit" in message
    )
