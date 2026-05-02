"""GitHub repository topics source adapter -- ecosystem positioning tags."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone

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


class GitHubRepositoryTopicsAdapter(SourceAdapter):
    """Fetch topic metadata for configured GitHub repositories."""

    @property
    def name(self) -> str:
        return "github_repository_topics"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def repositories(self) -> list[str]:
        return _string_list(self._config.get("repositories"), [])

    @property
    def api_url(self) -> str:
        configured = self._config.get("api_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().rstrip("/")
        return GITHUB_API

    @property
    def per_page(self) -> int:
        return min(_positive_int(self._config.get("per_page"), default=100), 100)

    @property
    def timeout(self) -> float:
        return _positive_float(self._config.get("timeout"), default=30.0)

    @property
    def token_env(self) -> str:
        configured = self._config.get("token_env")
        return configured.strip() if isinstance(configured, str) and configured.strip() else "GITHUB_TOKEN"

    @property
    def token(self) -> str | None:
        configured = self._config.get("github_token") or self._config.get("token")
        if configured:
            return str(configured)
        return os.environ.get(self.token_env)

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_repository_topics")
    async def _fetch_repository_topics(
        self,
        client: httpx.AsyncClient,
        repo: str,
    ) -> list[str] | None:
        """Fetch topics for one repository.

        Returns ``None`` for a missing repository so callers can continue with
        the rest of the configured repositories.
        """
        owner, name = _split_repo(repo)
        url = f"{self.api_url}/repos/{owner}/{name}/topics"
        try:
            resp = await client.get(url, params={"per_page": self.per_page})
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 404:
                return None
            if status == 429 or _is_github_rate_limit(e.response):
                retry_after = e.response.headers.get("Retry-After")
                retry_seconds = float(retry_after) if retry_after else None
                raise SourceRateLimitError(
                    f"Rate limit exceeded for repository topics: {repo}",
                    adapter_name=self.name,
                    retry_after=retry_seconds,
                ) from e
            if status in (401, 403):
                raise SourceAuthError(
                    f"Authentication failed (HTTP {status}) for repository topics: {repo}",
                    adapter_name=self.name,
                ) from e
            if 500 <= status < 600:
                raise SourceTransientError(
                    f"Server error (HTTP {status}) for repository topics: {repo}",
                    adapter_name=self.name,
                ) from e
            raise SourceTransientError(
                f"HTTP {status} for repository topics: {repo}",
                adapter_name=self.name,
            ) from e
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse repository topics response for: {repo}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, dict):
            raise SourceParseError(
                f"Unexpected repository topics response for: {repo}",
                adapter_name=self.name,
            )
        return _topic_list(data.get("names"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.repositories:
            return []

        signals: list[Signal] = []
        observed_at = datetime.now(timezone.utc)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            for repo in self.repositories:
                if len(signals) >= limit:
                    break
                try:
                    topics = await self._fetch_repository_topics(client, repo)
                except (SourceRateLimitError, SourceAuthError):
                    raise
                except (
                    SourceTransientError,
                    SourceParseError,
                    httpx.RequestError,
                    httpx.TimeoutException,
                ):
                    logger.warning(
                        "GitHub repository topics fetch failed for repo: %s",
                        repo,
                        exc_info=True,
                    )
                    continue

                if topics is None:
                    logger.info("GitHub repository not found while fetching topics: %s", repo)
                    continue

                signals.append(_to_signal(repo, topics, self.name, observed_at, self.api_url))

        return signals[:limit]


def _to_signal(
    repo: str,
    topics: list[str],
    adapter_name: str,
    observed_at: datetime,
    api_url: str,
) -> Signal:
    source_url = f"https://github.com/{repo}"
    topic_text = ", ".join(topics) if topics else "no repository topics"
    return Signal(
        id=_stable_id(repo, topics),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{repo} repository topics",
        content=f"{repo} is positioned with {topic_text}.",
        url=source_url,
        published_at=observed_at,
        fetched_at=observed_at,
        tags=_build_tags(repo, topics),
        credibility=0.65 if topics else 0.35,
        metadata={
            "repository": repo,
            "topics": topics,
            "topic_count": len(topics),
            "source_url": source_url,
            "api_url": f"{api_url}/repos/{repo}/topics",
            "observed_at": observed_at.isoformat(),
            "signal_role": "market",
        },
    )


def _string_list(value: object, default: list[str]) -> list[str]:
    if value is None:
        values = list(default)
    elif isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return list(default)

    seen: set[str] = set()
    normalized: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _topic_list(value: object) -> list[str]:
    return sorted(_string_list(value, []))


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _positive_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _split_repo(repo: str) -> tuple[str, str]:
    owner, _, name = repo.partition("/")
    if not owner or not name or "/" in name:
        raise SourceParseError(
            f"Invalid GitHub repository name: {repo}",
            adapter_name="github_repository_topics",
        )
    return owner, name


def _build_tags(repo: str, topics: list[str]) -> list[str]:
    tags: set[str] = {"github", "repository-topics"}
    tags.update(topics[:8])

    text = " ".join([repo, " ".join(topics)]).lower()
    keyword_map = {
        "ai": ["ai", "artificial intelligence", "openai", "anthropic"],
        "agent": ["agent", "agentic"],
        "llm": ["llm", "language model", "gpt", "claude"],
        "mcp": ["mcp", "model-context-protocol", "model context protocol"],
        "security": ["security", "vulnerability", "cve"],
        "typescript": ["typescript", "javascript"],
        "python": ["python"],
        "devtools": ["cli", "developer-tools", "sdk"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)

    return sorted(tags)[:10]


def _stable_id(repo: str, topics: list[str]) -> str:
    digest = hashlib.sha256(",".join(topics).encode("utf-8")).hexdigest()[:16]
    return f"github_repository_topics:{repo}:{digest}"


def _is_github_rate_limit(response: httpx.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    return response.status_code == 403 and remaining == "0"
