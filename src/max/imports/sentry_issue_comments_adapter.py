"""Sentry issue comments import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
SENTRY_API = "https://sentry.io/api/0"


class SentryIssueCommentsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        auth_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            auth_token
            if auth_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("auth_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("SENTRY_AUTH_TOKEN")
                )
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or SENTRY_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "sentry_issue_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def issue_ids(self) -> list[str]:
        return _strings(self._config.get("issue_ids") or self._config.get("issues") or self._config.get("issue_id"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    @property
    def per_issue_limit(self) -> int | None:
        value = self._config.get("per_issue_limit")
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @property
    def include_user_metadata(self) -> bool:
        return bool(self._config.get("include_user_metadata"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.issue_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for issue_id in self.issue_ids:
                if len(signals) >= limit:
                    break
                issue_limit = limit - len(signals)
                if self.per_issue_limit:
                    issue_limit = min(issue_limit, self.per_issue_limit)
                comments = await self._fetch_issue_comments(client, issue_id=issue_id, limit=issue_limit)
                signals.extend(
                    _comment_signal(
                        comment,
                        issue_id=issue_id,
                        adapter_name=self.name,
                        include_user_metadata=self.include_user_metadata,
                    )
                    for comment in comments
                    if isinstance(comment, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_issue_comments(
        self,
        client: httpx.AsyncClient,
        *,
        issue_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(comments) < limit:
            page_size = min(self.page_size, limit - len(comments))
            page_comments, cursor = await self._fetch_page(
                client,
                issue_id=issue_id,
                cursor=cursor,
                page_size=page_size,
            )
            if not page_comments:
                break
            comments.extend(page_comments[: limit - len(comments)])
            if not cursor or len(page_comments) < page_size:
                break
        return comments[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        issue_id: str,
        cursor: str | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"per_page": page_size}
        if cursor:
            params["cursor"] = cursor
        url = f"{self.api_url}/issues/{issue_id}/comments/"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-issue-comments-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Sentry issue comments fetch failed for issue %s", issue_id, exc_info=True)
            return [], None
        comments = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return comments, _next_cursor(response)


SentryIssueCommentAdapter = SentryIssueCommentsAdapter


def _comment_signal(
    comment: dict[str, Any],
    *,
    issue_id: str,
    adapter_name: str,
    include_user_metadata: bool,
) -> Signal:
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    author = _optional(
        comment.get("authorName")
        or comment.get("author_name")
        or user.get("name")
        or user.get("username")
        or user.get("email")
        or user.get("id")
    )
    comment_id = _text(comment.get("id"))
    message = _text(comment.get("data") or comment.get("text") or comment.get("message"))
    issue_url = _optional(comment.get("issueUrl") or comment.get("issue_url"))
    comment_url = _optional(comment.get("permalink") or comment.get("url") or comment.get("webUrl") or comment.get("web_url"))
    metadata: dict[str, Any] = {
        "sentry_issue_id": issue_id,
        "sentry_comment_id": comment.get("id"),
        "message": message,
        "author": author,
        "user": _user_summary(user),
        "created_at": comment.get("dateCreated") or comment.get("created_at"),
        "issue_url": issue_url,
        "comment_url": comment_url,
        "raw": comment,
    }
    if include_user_metadata:
        metadata["user_metadata"] = user
    return Signal(
        id=f"sentry-issue-comment:{issue_id}:{comment_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"Sentry issue {issue_id} comment",
        content=message[:1000],
        url=comment_url or issue_url or "",
        author=author,
        published_at=_parse_dt(comment.get("dateCreated") or comment.get("created_at")),
        tags=sorted({"sentry", "issue-comment"} - {""})[:10],
        credibility=0.65,
        metadata=metadata,
    )


def _next_cursor(response: httpx.Response) -> str | None:
    next_link = response.links.get("next") if response.links else None
    if not next_link:
        return None
    if _text(next_link.get("results")).lower() == "false":
        return None
    cursor = _optional(next_link.get("cursor"))
    if cursor:
        return cursor
    next_url = _optional(next_link.get("url"))
    if not next_url:
        return None
    return _optional(str(httpx.URL(next_url).params.get("cursor")))


def _user_summary(user: dict[str, Any]) -> dict[str, Any]:
    return {
        key: user.get(key)
        for key in ("id", "name", "username", "email")
        if user.get(key) is not None
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
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
