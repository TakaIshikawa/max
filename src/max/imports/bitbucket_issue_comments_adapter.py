"""Bitbucket issue comments import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
BITBUCKET_API = "https://api.bitbucket.org/2.0"


class BitbucketIssueCommentsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        username: str | None = None,
        app_password: str | None = None,
        bearer_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.username = username if username is not None else (_optional(self._config.get("username")) or os.getenv("BITBUCKET_USERNAME"))
        self.app_password = app_password if app_password is not None else (
            _optional(self._config.get("app_password")) or os.getenv("BITBUCKET_APP_PASSWORD")
        )
        self.bearer_token = bearer_token if bearer_token is not None else (
            token
            or _optional(self._config.get("bearer_token"))
            or _optional(self._config.get("token"))
            or os.getenv("BITBUCKET_BEARER_TOKEN")
            or os.getenv("BITBUCKET_TOKEN")
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or BITBUCKET_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "bitbucket_issue_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def workspace(self) -> str | None:
        return _optional(self._config.get("workspace"))

    @property
    def repo_slug(self) -> str | None:
        repository = _optional(self._config.get("repo_slug") or self._config.get("repository"))
        if repository and "/" in repository:
            return repository.rsplit("/", 1)[1]
        return repository

    @property
    def issue_ids(self) -> list[str]:
        return _strings(self._config.get("issue_ids") or self._config.get("issue_id"))

    @property
    def page_len(self) -> int:
        return _positive_int(self._config.get("pagelen") or self._config.get("page_len"), default=30, maximum=100)

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.username and self.app_password))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.workspace and self.repo_slug and self.issue_ids and self._has_auth):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rows: list[tuple[str, dict[str, Any]]] = []
            for issue_id in self.issue_ids:
                if len(rows) >= limit:
                    break
                comments = await self._fetch_comments(client, issue_id=issue_id, limit=limit - len(rows))
                if comments is None:
                    return []
                rows.extend((issue_id, comment) for comment in comments)
            return [_comment_signal(comment, self.workspace, self.repo_slug, issue_id, self.name) for issue_id, comment in rows[:limit]]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_comments(self, client: httpx.AsyncClient, *, issue_id: str, limit: int) -> list[dict[str, Any]] | None:
        comments: list[dict[str, Any]] = []
        url: str | None = f"{self.api_url}/repositories/{self.workspace}/{self.repo_slug}/issues/{issue_id}/comments"
        params: dict[str, Any] | None = {"pagelen": min(self.page_len, limit)}
        while url and len(comments) < limit:
            body = await self._get(client, url, params=params)
            if body is None:
                return None
            values = body.get("values") if isinstance(body.get("values"), list) else []
            if not values:
                break
            comments.extend(item for item in values if isinstance(item, dict))
            url = _optional(body.get("next"))
            params = None
        return comments[:limit]

    async def _get(self, client: httpx.AsyncClient, url: str, *, params: dict[str, Any] | None) -> dict[str, Any] | None:
        headers = {"Accept": "application/json", "User-Agent": "max-bitbucket-issue-comments-import/1"}
        auth = None
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            auth = httpx.BasicAuth(self.username or "", self.app_password or "")
        try:
            response = await client.get(url, headers=headers, auth=auth, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Bitbucket issue comment fetch failed for %s", url, exc_info=True)
            return None
        return body if isinstance(body, dict) else {}


BitbucketIssueCommentAdapter = BitbucketIssueCommentsAdapter


def _comment_signal(comment: dict[str, Any], workspace: str, repo_slug: str, issue_id: str, adapter_name: str) -> Signal:
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    content = comment.get("content") if isinstance(comment.get("content"), dict) else {}
    links = comment.get("links") if isinstance(comment.get("links"), dict) else {}
    comment_id = _text(comment.get("id")) or _text(comment.get("created_on"))
    return Signal(
        id=f"bitbucket-issue-comment:{workspace}:{repo_slug}:{issue_id}:{comment_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{workspace}/{repo_slug} issue #{issue_id} comment",
        content=_text(content.get("raw") or content.get("html") or content.get("markup"))[:1000],
        url=_link_href(links.get("html")),
        author=_optional(user.get("display_name") or user.get("nickname") or user.get("username")),
        published_at=_parse_dt(comment.get("created_on")),
        tags=sorted({"bitbucket", "issue", "comment"} - {""})[:10],
        credibility=0.6,
        metadata={
            "comment_id": comment.get("id"),
            "workspace": workspace,
            "repository": repo_slug,
            "issue_id": issue_id,
            "content": content,
            "author": _summary(user),
            "created_on": comment.get("created_on"),
            "updated_on": comment.get("updated_on"),
            "links": links,
            "raw": comment,
        },
    )


def _link_href(value: object) -> str:
    return _text(value.get("href")) if isinstance(value, dict) else ""


def _summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "id": value.get("id"),
        "uuid": value.get("uuid"),
        "display_name": value.get("display_name"),
        "nickname": value.get("nickname"),
        "username": value.get("username"),
        "links": value.get("links"),
    }


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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
