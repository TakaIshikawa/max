"""Jira issue comments import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class JiraIssueCommentsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.base_url = (base_url or _optional(self._config.get("base_url")) or os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("JIRA_EMAIL") or os.getenv("JIRA_USERNAME"))
        self.token = token if token is not None else (_optional(self._config.get("token")) or _optional(self._config.get("api_token")) or os.getenv("JIRA_API_TOKEN"))
        self._client = client

    @property
    def name(self) -> str:
        return "jira_issue_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def issue_keys(self) -> list[str]:
        return _strings(self._config.get("issue_keys") or self._config.get("issue_key"))

    @property
    def expand(self) -> list[str]:
        return _strings(self._config.get("expand"))

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=50, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.email and self.token and self.issue_keys):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for issue_key in self.issue_keys:
                if len(signals) >= limit:
                    break
                comments = await self._fetch_issue_comments(
                    client,
                    issue_key=issue_key,
                    limit=limit - len(signals),
                )
                for comment in comments:
                    signal = _comment_signal(comment, issue_key, self.name, self.base_url, seen)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_issue_comments(
        self,
        client: httpx.AsyncClient,
        *,
        issue_key: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        start_at = 0
        while len(comments) < limit:
            max_results = min(self.per_page, limit - len(comments))
            body = await self._fetch_page(client, issue_key=issue_key, start_at=start_at, max_results=max_results)
            page = body.get("comments") if isinstance(body.get("comments"), list) else []
            if not page:
                break
            comments.extend(item for item in page if isinstance(item, dict))
            total = _int(body.get("total"))
            start_at = _int(body.get("startAt"), start_at) + len(page)
            if start_at >= total or len(page) < max_results:
                break
        return comments[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        issue_key: str,
        start_at: int,
        max_results: int,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"startAt": start_at, "maxResults": max_results}
        if self.expand:
            params["expand"] = ",".join(self.expand)
        try:
            response = await client.get(
                f"{self.base_url}/rest/api/3/issue/{issue_key}/comment",
                auth=(self.email or "", self.token or ""),
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Jira issue comment fetch failed for %s", issue_key, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


JiraIssueCommentsAdapter = JiraIssueCommentsImportAdapter


def _comment_signal(
    comment: dict[str, Any],
    issue_key: str,
    adapter_name: str,
    base_url: str,
    seen: set[str],
) -> Signal | None:
    comment_id = _optional(comment.get("id"))
    if not comment_id:
        return None
    external_id = f"jira-issue-comment:{issue_key}:{comment_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    author = comment.get("author") if isinstance(comment.get("author"), dict) else {}
    rendered_body = _text(comment.get("renderedBody"))
    body = rendered_body or _jira_document_text(comment.get("body")) or _text(comment.get("body"))
    updated = _text(comment.get("updated")) or _text(comment.get("created"))
    self_url = _text(comment.get("self"))
    visibility = _visibility(comment)

    return Signal(
        id=external_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{issue_key} issue comment",
        content=body[:1000],
        url=self_url or (f"{base_url}/browse/{issue_key}" if issue_key else base_url),
        author=_text(author.get("displayName")) or _text(author.get("emailAddress")) or None,
        published_at=_parse_dt(updated),
        tags=sorted({"jira", "issue-comment", visibility} - {""})[:10],
        credibility=0.65,
        metadata={
            "issue_key": issue_key,
            "comment_id": comment_id,
            "author": {
                "account_id": author.get("accountId"),
                "display_name": author.get("displayName"),
                "email": author.get("emailAddress"),
                "active": author.get("active"),
            },
            "body": body,
            "rendered_body": rendered_body or None,
            "created_at": comment.get("created"),
            "updated_at": updated,
            "visibility": visibility,
            "self_url": self_url,
            "raw": comment,
        },
    )


def _visibility(comment: dict[str, Any]) -> str:
    visibility = comment.get("visibility") if isinstance(comment.get("visibility"), dict) else {}
    return _text(visibility.get("type") or visibility.get("value") or comment.get("visibility"))


def _jira_document_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            for child in node.get("content", []) if isinstance(node.get("content"), list) else []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return " ".join(part.strip() for part in parts if part.strip())


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
