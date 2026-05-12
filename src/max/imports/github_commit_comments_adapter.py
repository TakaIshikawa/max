"""GitHub commit comments import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubCommitCommentsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        repository: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("GITHUB_TOKEN"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or GITHUB_API).rstrip("/")
        self.owner = owner or _optional(self._config.get("owner"))
        self.repo = repo or _optional(self._config.get("repo"))
        self.repository = repository or _optional(self._config.get("repository")) or _optional(self._config.get("repo_full_name"))
        self._client = client

    @property
    def name(self) -> str:
        return "github_commit_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def repositories(self) -> list[str]:
        configured = _strings(self._config.get("repositories") or self._config.get("repos"))
        if configured:
            return configured
        if self.repository:
            return [self.repository]
        if self.owner and self.repo:
            return [f"{self.owner}/{self.repo}"]
        return []

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    @property
    def per_repo_limit(self) -> int | None:
        value = self._config.get("per_repo_limit")
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        repositories = [_owner_repo(repository) for repository in self.repositories]
        repositories = [repository for repository in repositories if repository]
        if limit <= 0 or not self.token or not repositories:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for repository in repositories:
                if len(signals) >= limit:
                    break
                repo_limit = limit - len(signals)
                if self.per_repo_limit:
                    repo_limit = min(repo_limit, self.per_repo_limit)
                comments = await self._fetch_repository(client, repository=repository, limit=repo_limit)
                signals.extend(
                    _comment_signal(comment, repository, self.name)
                    for comment in comments
                    if isinstance(comment, dict)
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
        comments: list[dict[str, Any]] = []
        page = 1
        while len(comments) < limit:
            page_size = min(self.page_size, limit - len(comments))
            page_comments = await self._fetch_page(client, repository=repository, page=page, page_size=page_size)
            if not page_comments:
                break
            comments.extend(page_comments)
            if len(page_comments) < page_size:
                break
            page += 1
        return comments[:limit]

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
                f"{self.api_url}/repos/{repository}/comments",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "max-github-commit-comments-import/1",
                },
                params=self._params(page=page, page_size=page_size),
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub commit comments fetch failed for %s", repository, exc_info=True)
            return []
        return [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []

    def _params(self, *, page: int, page_size: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "per_page": page_size}
        since = _optional(self._config.get("since"))
        if since:
            params["since"] = since
        return params


GitHubCommitCommentAdapter = GitHubCommitCommentsAdapter


def _comment_signal(comment: dict[str, Any], repository: str, adapter_name: str) -> Signal:
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    author = _optional(user.get("login") or user.get("name") or user.get("email"))
    comment_id = _text(comment.get("id") or comment.get("node_id"))
    commit_sha = _text(comment.get("commit_id") or comment.get("commit_sha"))
    path = _text(comment.get("path"))
    body = _text(comment.get("body"))
    return Signal(
        id=f"github-commit-comment:{repository}:{comment_id or commit_sha}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{repository} commit {commit_sha[:7] or '?'} comment",
        content=body[:1000],
        url=_text(comment.get("html_url")),
        author=author,
        published_at=_parse_dt(comment.get("created_at")),
        tags=sorted({"github", "commit-comment", path} - {""})[:10],
        credibility=0.65,
        metadata={
            "github_commit_comment_id": comment.get("id"),
            "node_id": comment.get("node_id"),
            "repository": repository,
            "commit_sha": commit_sha or None,
            "comment_url": comment.get("html_url") or comment.get("url"),
            "api_url": comment.get("url"),
            "author": {
                "login": user.get("login"),
                "id": user.get("id"),
                "node_id": user.get("node_id"),
                "type": user.get("type"),
                "html_url": user.get("html_url"),
            },
            "body": body,
            "path": comment.get("path"),
            "position": comment.get("position"),
            "line": comment.get("line"),
            "created_at": comment.get("created_at"),
            "updated_at": comment.get("updated_at"),
            "html_url": comment.get("html_url"),
            "raw": comment,
        },
    )


def _owner_repo(value: str) -> str | None:
    text = value.strip()
    if "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    owner = owner.strip()
    repo = repo.strip()
    return f"{owner}/{repo}" if owner and repo else None


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


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
