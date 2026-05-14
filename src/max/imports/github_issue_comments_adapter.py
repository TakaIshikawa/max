"""GitHub issue comments import adapter."""

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


class GitHubIssueCommentsAdapter(SourceAdapter):
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
        configured_repository = repository or _optional(self._config.get("repository")) or _optional(self._config.get("repo_full_name"))
        repo_owner, repo_name = _split_repository(configured_repository)
        self.owner = owner or _optional(self._config.get("owner")) or repo_owner
        self.repo = repo or _optional(self._config.get("repo")) or repo_name
        self._client = client

    @property
    def name(self) -> str:
        return "github_issue_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def issue_numbers(self) -> list[int]:
        return _positive_ints(self._config.get("issue_numbers") or self._config.get("issue_number"))

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.token and self.owner and self.repo and self.issue_numbers):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rows: list[tuple[int, dict[str, Any]]] = []
            for issue_number in self.issue_numbers:
                if len(rows) >= limit:
                    break
                comments = await self._fetch_issue_comments(client, issue_number=issue_number, limit=limit - len(rows))
                if comments is None:
                    return []
                rows.extend((issue_number, comment) for comment in comments)
            repository = f"{self.owner}/{self.repo}"
            return [_comment_signal(comment, repository, issue_number, self.name) for issue_number, comment in rows[:limit]]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_issue_comments(
        self,
        client: httpx.AsyncClient,
        *,
        issue_number: int,
        limit: int,
    ) -> list[dict[str, Any]] | None:
        comments: list[dict[str, Any]] = []
        page = 1
        while len(comments) < limit:
            page_size = min(self.per_page, limit - len(comments))
            page_comments = await self._fetch_page(client, issue_number=issue_number, page=page, page_size=page_size)
            if page_comments is None:
                return None
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
        issue_number: int,
        page: int,
        page_size: int,
    ) -> list[dict[str, Any]] | None:
        try:
            response = await client.get(
                f"{self.api_url}/repos/{self.owner}/{self.repo}/issues/{issue_number}/comments",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "max-github-issue-comments-import/1",
                },
                params={"page": page, "per_page": page_size},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub issue comments fetch failed", exc_info=True)
            return None
        return [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []


GitHubIssueCommentAdapter = GitHubIssueCommentsAdapter


def _comment_signal(comment: dict[str, Any], repository: str, issue_number: int, adapter_name: str) -> Signal:
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    author = _optional(user.get("login") or user.get("name") or user.get("email"))
    comment_id = _text(comment.get("id") or comment.get("node_id") or comment.get("created_at"))
    return Signal(
        id=f"github-issue-comment:{repository}:{issue_number}:{comment_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{repository} issue #{issue_number} comment",
        content=_text(comment.get("body"))[:1000],
        url=_text(comment.get("html_url")),
        author=author,
        published_at=_parse_dt(comment.get("created_at")),
        tags=["github", "issue", "comment"],
        credibility=0.65,
        metadata={
            "github_issue_comment_id": comment.get("id"),
            "node_id": comment.get("node_id"),
            "repository": repository,
            "issue_number": issue_number,
            "author": {
                "login": user.get("login"),
                "id": user.get("id"),
                "node_id": user.get("node_id"),
                "type": user.get("type"),
                "html_url": user.get("html_url"),
            },
            "body": comment.get("body"),
            "url": comment.get("url"),
            "html_url": comment.get("html_url"),
            "issue_url": comment.get("issue_url"),
            "created_at": comment.get("created_at"),
            "updated_at": comment.get("updated_at"),
            "raw": comment,
        },
    )


def _split_repository(value: str | None) -> tuple[str | None, str | None]:
    if not value or "/" not in value:
        return None, None
    owner, repo = value.split("/", 1)
    return (_optional(owner), _optional(repo))


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


def _positive_ints(value: object) -> list[int]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list):
        return []
    numbers: list[int] = []
    for item in value:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number > 0:
            numbers.append(number)
    return numbers


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
