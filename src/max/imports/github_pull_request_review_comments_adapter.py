"""GitHub pull request review comments import adapter."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubPullRequestReviewCommentsAdapter(SourceAdapter):
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
        return "github_pull_request_review_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.token and self.owner and self.repo):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            comments: list[dict[str, Any]] = []
            page = 1
            while len(comments) < limit:
                page_size = min(self.per_page, limit - len(comments))
                page_comments = await self._fetch_page(client, page=page, page_size=page_size)
                if not page_comments:
                    break
                comments.extend(page_comments)
                if len(page_comments) < page_size:
                    break
                page += 1
        finally:
            if close_client:
                await client.aclose()

        repository = f"{self.owner}/{self.repo}"
        return [_comment_signal(comment, repository, self.name) for comment in comments[:limit] if isinstance(comment, dict)]

    async def _fetch_page(self, client: httpx.AsyncClient, *, page: int, page_size: int) -> list[dict[str, Any]]:
        try:
            response = await client.get(
                f"{self.api_url}/repos/{self.owner}/{self.repo}/pulls/comments",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "max-github-pr-review-comments-import/1",
                },
                params=self._params(page=page, page_size=page_size),
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub pull request review comments fetch failed", exc_info=True)
            return []
        return [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []

    def _params(self, *, page: int, page_size: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "per_page": page_size}
        for key in ("sort", "direction", "since"):
            value = _optional(self._config.get(key))
            if value:
                params[key] = value
        return params


GitHubPullRequestReviewCommentAdapter = GitHubPullRequestReviewCommentsAdapter


def _comment_signal(comment: dict[str, Any], repository: str, adapter_name: str) -> Signal:
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    author = _optional(user.get("login") or user.get("name") or user.get("email"))
    comment_id = _text(comment.get("id") or comment.get("node_id"))
    pr_number = _pull_request_number(comment)
    path = _text(comment.get("path"))
    body = _text(comment.get("body"))
    return Signal(
        id=f"github-pr-review-comment:{repository}:{comment_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{repository} PR {pr_number or '?'} review comment".strip(),
        content=body[:1000],
        url=_text(comment.get("html_url")),
        author=author,
        published_at=_parse_dt(comment.get("created_at")),
        tags=sorted({"github", "pull-request", "review-comment", path} - {""})[:10],
        credibility=0.65,
        metadata={
            "github_pull_request_review_comment_id": comment.get("id"),
            "node_id": comment.get("node_id"),
            "repository": repository,
            "pull_request_number": pr_number,
            "pull_request_url": comment.get("pull_request_url"),
            "comment_url": comment.get("html_url") or comment.get("url"),
            "api_url": comment.get("url"),
            "pull_request_review_id": comment.get("pull_request_review_id"),
            "author": {
                "login": user.get("login"),
                "id": user.get("id"),
                "node_id": user.get("node_id"),
                "type": user.get("type"),
                "html_url": user.get("html_url"),
            },
            "body": body,
            "path": comment.get("path"),
            "diff_hunk": comment.get("diff_hunk"),
            "position": comment.get("position"),
            "original_position": comment.get("original_position"),
            "line": comment.get("line"),
            "original_line": comment.get("original_line"),
            "side": comment.get("side"),
            "commit_id": comment.get("commit_id"),
            "original_commit_id": comment.get("original_commit_id"),
            "created_at": comment.get("created_at"),
            "updated_at": comment.get("updated_at"),
            "raw": comment,
        },
    )


def _pull_request_number(comment: dict[str, Any]) -> int | None:
    for value in (comment.get("pull_request_url"), comment.get("html_url")):
        text = _text(value)
        match = re.search(r"/pulls?/(\d+)(?:\b|[/#?])", text)
        if match:
            return int(match.group(1))
    links = comment.get("_links") if isinstance(comment.get("_links"), dict) else {}
    pull_request = links.get("pull_request") if isinstance(links.get("pull_request"), dict) else {}
    href = _text(pull_request.get("href"))
    match = re.search(r"/pulls?/(\d+)(?:\b|[/#?])", href)
    return int(match.group(1)) if match else None


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


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
