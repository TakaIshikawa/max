"""Linear issue comment import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"


class LinearCommentsAdapter(SourceAdapter):
    """Fetch Linear issue comments and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str = LINEAR_GRAPHQL_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("LINEAR_API_KEY"))
        self.api_url = api_url
        self._client = client

    @property
    def name(self) -> str:
        return "linear_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def issue_id(self) -> str | None:
        return _optional(self._config.get("issue_id"))

    @property
    def team_id(self) -> str | None:
        return _optional(self._config.get("team_id"))

    @property
    def updated_since(self) -> str | None:
        return _optional(self._config.get("updated_since"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=50, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            comments: list[dict[str, Any]] = []
            cursor: str | None = None
            while len(comments) < limit:
                page_size = min(self.page_size, limit - len(comments))
                body = await self._post(client, first=page_size, after=cursor)
                nodes, cursor, has_next_page = _comments_page(body)
                if not nodes:
                    break
                comments.extend(nodes)
                if not has_next_page:
                    break
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            signal = _comment_signal(comment, self.name, seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _post(self, client: httpx.AsyncClient, *, first: int, after: str | None) -> dict[str, Any]:
        try:
            response = await client.post(
                self.api_url,
                json={
                    "query": COMMENTS_QUERY,
                    "variables": {
                        "first": first,
                        "after": after,
                        "filter": self._filter(),
                    },
                },
                headers={
                    "Authorization": self.token or "",
                    "Content-Type": "application/json",
                    "User-Agent": "max-linear-comments-import/1",
                },
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Linear comment fetch failed", exc_info=True)
            return {}
        if not isinstance(body, dict) or body.get("errors"):
            if isinstance(body, dict) and body.get("errors"):
                logger.warning("Linear comment fetch returned GraphQL errors: %s", body.get("errors"))
            return {}
        return body

    def _filter(self) -> dict[str, Any]:
        filters: list[dict[str, Any]] = []
        if self.issue_id:
            filters.append({"issue": {"id": {"eq": self.issue_id}}})
        if self.team_id:
            filters.append({"issue": {"team": {"id": {"eq": self.team_id}}}})
        if self.updated_since:
            filters.append({"updatedAt": {"gte": self.updated_since}})
        if not filters:
            return {}
        return {"and": filters}


LinearIssueCommentsAdapter = LinearCommentsAdapter


COMMENTS_QUERY = """
query MaxLinearIssueComments($first: Int!, $after: String, $filter: CommentFilter) {
  comments(first: $first, after: $after, filter: $filter, orderBy: updatedAt) {
    nodes {
      id
      body
      url
      createdAt
      updatedAt
      user { id name displayName email url }
      issue {
        id
        identifier
        title
        url
        team { id key name }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def _comments_page(body: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None, bool]:
    comments = ((body.get("data") or {}).get("comments") or {}) if isinstance(body.get("data"), dict) else {}
    if not isinstance(comments, dict):
        return [], None, False
    nodes = comments.get("nodes")
    page_info = comments.get("pageInfo") if isinstance(comments.get("pageInfo"), dict) else {}
    return (
        [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else [],
        _optional(page_info.get("endCursor")),
        bool(page_info.get("hasNextPage")),
    )


def _comment_signal(comment: dict[str, Any], adapter_name: str, seen: set[str]) -> Signal | None:
    comment_id = _optional(comment.get("id"))
    if not comment_id or comment_id in seen:
        return None
    seen.add(comment_id)
    issue = comment.get("issue") if isinstance(comment.get("issue"), dict) else {}
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    team = issue.get("team") if isinstance(issue.get("team"), dict) else {}
    issue_ref = _optional(issue.get("identifier")) or _optional(issue.get("id")) or "Linear issue"
    author = _optional(user.get("displayName")) or _optional(user.get("name")) or _optional(user.get("email"))
    return Signal(
        id=f"linear-comment:{comment_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{issue_ref} comment",
        content=_text(comment.get("body"))[:1000],
        url=_optional(comment.get("url")) or _optional(issue.get("url")) or "",
        author=author,
        published_at=_parse_dt(comment.get("createdAt")),
        tags=sorted({"linear", "comment", _text(team.get("key"))} - {""})[:10],
        credibility=0.65,
        metadata={
            "linear_comment_id": comment_id,
            "linear_issue_id": issue.get("id"),
            "issue_identifier": issue.get("identifier"),
            "issue_title": issue.get("title"),
            "issue_url": issue.get("url"),
            "team_id": team.get("id"),
            "team_key": team.get("key"),
            "team_name": team.get("name"),
            "author": {
                "id": user.get("id"),
                "name": user.get("name") or user.get("displayName"),
                "display_name": user.get("displayName"),
                "email": user.get("email"),
                "url": user.get("url"),
            },
            "created_at": comment.get("createdAt"),
            "updated_at": comment.get("updatedAt"),
            "raw": comment,
        },
    )


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    return min(value, maximum) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
