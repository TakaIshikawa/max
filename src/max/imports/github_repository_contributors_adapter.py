"""GitHub repository contributors import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubRepositoryContributorsAdapter(SourceAdapter):
    """Fetch GitHub repository contributors and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        base_url: str | None = None,
        repository: str | dict[str, Any] | None = None,
        owner: str | None = None,
        repo: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("token"))
                or os.getenv("GITHUB_TOKEN")
                or os.getenv("GITHUB_ACCESS_TOKEN")
            )
        )
        self.api_url = (
            api_url
            or base_url
            or _optional(self._config.get("api_url"))
            or _optional(self._config.get("base_url"))
            or GITHUB_API
        ).rstrip("/")
        self._repository = repository
        self._owner = owner
        self._repo = repo
        self._client = client

    @property
    def name(self) -> str:
        return "github_repository_contributors_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def repositories(self) -> list[str]:
        explicit = _repository_from_parts(self._owner, self._repo) or _repository(self._repository)
        if explicit:
            return [explicit]

        configured = (
            self._config.get("repository")
            or self._config.get("repositories")
            or self._config.get("repo_full_name")
            or self._config.get("repos")
            or os.getenv("GITHUB_REPOSITORY")
        )
        repositories = [_repository(value) for value in _values(configured)]
        from_parts = _repository_from_parts(self._config.get("owner"), self._config.get("repo"))
        if from_parts:
            repositories.insert(0, from_parts)
        return _dedupe([repo for repo in repositories if repo])

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page") or self._config.get("page_size"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.repositories:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for repository in self.repositories:
                if len(signals) >= limit:
                    break
                contributors = await self._fetch_repository(
                    client,
                    repository=repository,
                    limit=limit - len(signals),
                )
                signals.extend(
                    _contributor_signal(contributor, repository=repository, adapter_name=self.name)
                    for contributor in contributors
                    if isinstance(contributor, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        *,
        repository: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        contributors: list[dict[str, Any]] = []
        page = 1
        while len(contributors) < limit:
            page_size = min(self.per_page, limit - len(contributors))
            page_contributors = await self._fetch_page(
                client,
                repository=repository,
                page=page,
                page_size=page_size,
            )
            if not page_contributors:
                break
            contributors.extend(page_contributors[: limit - len(contributors)])
            if len(page_contributors) < page_size:
                break
            page += 1
        return contributors[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        repository: str,
        page: int,
        page_size: int,
    ) -> list[dict[str, Any]]:
        try:
            response = await client.get(
                f"{self.api_url}/repos/{_encode_repository(repository)}/contributors",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "max-github-repository-contributors-import/1",
                },
                params={"per_page": page_size, "page": page},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub repository contributors fetch failed for %s", repository, exc_info=True)
            return []
        return [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []


GitHubRepositoryContributorAdapter = GitHubRepositoryContributorsAdapter


def _contributor_signal(contributor: dict[str, Any], *, repository: str, adapter_name: str) -> Signal:
    login = _optional(contributor.get("login") or contributor.get("name") or contributor.get("email"))
    contributor_id = _optional(contributor.get("id")) or _optional(contributor.get("node_id")) or login or "unknown"
    contributions = _int(contributor.get("contributions"))
    return Signal(
        id=f"github-repository-contributor:{repository}:{contributor_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{repository} contributor {login or contributor_id}",
        content=_content(login=login, repository=repository, contributions=contributions),
        url=_text(contributor.get("html_url") or contributor.get("url")),
        author=login,
        published_at=_parse_dt(contributor.get("created_at")),
        tags=sorted({"github", "repository-contributor", repository, login or ""} - {""})[:10],
        credibility=0.64,
        metadata={
            "signal_role": "ecosystem_health",
            "repository": repository,
            "repository_owner": repository.split("/", 1)[0],
            "repository_name": repository.split("/", 1)[1],
            "github_contributor_id": contributor.get("id"),
            "node_id": contributor.get("node_id"),
            "login": login,
            "name": contributor.get("name"),
            "type": contributor.get("type"),
            "site_admin": contributor.get("site_admin"),
            "contributions": contributions,
            "avatar_url": contributor.get("avatar_url"),
            "gravatar_id": contributor.get("gravatar_id"),
            "url": contributor.get("url"),
            "html_url": contributor.get("html_url"),
            "followers_url": contributor.get("followers_url"),
            "following_url": contributor.get("following_url"),
            "repos_url": contributor.get("repos_url"),
            "raw": contributor,
        },
    )


def _content(*, login: str | None, repository: str, contributions: int) -> str:
    parts = [f"GitHub contributor {login or 'unknown'} for {repository}"]
    if contributions:
        parts.append(f"{contributions} contributions")
    return "; ".join(parts)


def _repository_from_parts(owner: object, repo: object) -> str | None:
    owner_text = _optional(owner)
    repo_text = _optional(repo)
    return f"{owner_text}/{repo_text}" if owner_text and repo_text else None


def _repository(value: object) -> str | None:
    if isinstance(value, dict):
        from_parts = _repository_from_parts(value.get("owner"), value.get("repo") or value.get("name"))
        if from_parts:
            return from_parts
        value = value.get("repository") or value.get("full_name") or value.get("repo_full_name")
    text = _optional(value)
    if not text or "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    return f"{owner}/{repo}" if owner and repo else None


def _encode_repository(repository: str) -> str:
    owner, repo = repository.split("/", 1)
    return f"{quote(owner, safe='')}/{quote(repo, safe='')}"


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _values(value: object) -> list[object]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",")]
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list | tuple | set):
        return list(value)
    return []


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
