"""GitHub Discussion Comments source adapter -- direct user feedback in threads."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import (
    AdapterCircuitOpenError,
    AdapterFetchError,
    AdapterRateLimitError,
    SourceAdapter,
    fetch_with_retry,
)
from max.sources.errors import SourceParseError
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

_COMMENTS_QUERY = """
query DiscussionComments(
  $owner: String!,
  $name: String!,
  $number: Int!,
  $first: Int!,
  $after: String
) {
  repository(owner: $owner, name: $name) {
    discussion(number: $number) {
      number
      title
      url
      category {
        name
        slug
      }
      labels(first: 20) {
        nodes {
          name
        }
      }
      comments(first: $first, after: $after) {
        totalCount
        nodes {
          id
          bodyText
          url
          createdAt
          updatedAt
          upvoteCount
          author {
            login
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
"""


class GitHubDiscussionCommentsAdapter(SourceAdapter):
    """Fetch comments from configured GitHub Discussions."""

    @property
    def name(self) -> str:
        return "github_discussion_comments"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def repositories(self) -> list[str]:
        return _string_list(self._config.get("repositories"), [])

    @property
    def discussion_numbers(self) -> dict[str, list[int]]:
        return _discussion_number_map(self._config.get("discussion_numbers"), self.repositories)

    @property
    def labels(self) -> list[str]:
        return _string_list(self._config.get("labels"), [])

    @property
    def api_url(self) -> str:
        configured = self._config.get("api_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().rstrip("/")
        return GITHUB_API

    @property
    def max_comments_per_discussion(self) -> int:
        return _positive_int(self._config.get("max_comments_per_discussion"), default=100)

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

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        repo: str,
        number: int,
        *,
        first: int,
        after: str | None,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any]]:
        owner, name = _split_repo(repo)
        response = await fetch_with_retry(
            f"{self.api_url}/graphql",
            client,
            adapter_name=self.name,
            method="POST",
            json={
                "query": _COMMENTS_QUERY,
                "variables": {
                    "owner": owner,
                    "name": name,
                    "number": number,
                    "first": first,
                    "after": after,
                },
            },
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise SourceParseError(
                f"Unexpected GitHub discussion comments response for {repo}#{number}",
                adapter_name=self.name,
            )

        errors = payload.get("errors") or []
        if errors:
            raise SourceParseError(
                f"GitHub GraphQL error for discussion comments: {_graphql_error_message(errors)}",
                adapter_name=self.name,
            )

        discussion = (
            payload.get("data", {})
            .get("repository", {})
            .get("discussion")
        )
        if discussion is None:
            return None, [], {"hasNextPage": False, "endCursor": None}
        if not isinstance(discussion, dict):
            raise SourceParseError(
                f"Unexpected GitHub discussion payload for {repo}#{number}",
                adapter_name=self.name,
            )

        comments = discussion.get("comments") or {}
        if not isinstance(comments, dict):
            raise SourceParseError(
                f"Unexpected GitHub discussion comments payload for {repo}#{number}",
                adapter_name=self.name,
            )
        nodes = comments.get("nodes") or []
        page_info = comments.get("pageInfo") or {}
        if not isinstance(nodes, list) or not isinstance(page_info, dict):
            raise SourceParseError(
                f"Unexpected GitHub discussion comments page for {repo}#{number}",
                adapter_name=self.name,
            )
        return discussion, nodes, page_info

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.repositories or not self.discussion_numbers:
            return []

        signals: list[Signal] = []
        seen_urls: set[str] = set()
        label_filter = {label.lower() for label in self.labels}
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for repo in self.repositories:
                for number in self.discussion_numbers.get(repo, []):
                    if len(signals) >= limit:
                        return signals[:limit]
                    await self._fetch_discussion_comments(
                        client,
                        repo,
                        number,
                        signals=signals,
                        seen_urls=seen_urls,
                        label_filter=label_filter,
                        limit=limit,
                    )

        return signals[:limit]

    async def _fetch_discussion_comments(
        self,
        client: httpx.AsyncClient,
        repo: str,
        number: int,
        *,
        signals: list[Signal],
        seen_urls: set[str],
        label_filter: set[str],
        limit: int,
    ) -> None:
        after: str | None = None
        fetched_for_discussion = 0
        while len(signals) < limit and fetched_for_discussion < self.max_comments_per_discussion:
            page_size = min(100, limit - len(signals), self.max_comments_per_discussion - fetched_for_discussion)
            if page_size <= 0:
                break
            try:
                discussion, comments, page_info = await self._fetch_page(
                    client,
                    repo,
                    number,
                    first=page_size,
                    after=after,
                )
            except (
                AdapterCircuitOpenError,
                AdapterFetchError,
                AdapterRateLimitError,
                SourceParseError,
                httpx.RequestError,
                ValueError,
                TypeError,
            ):
                logger.warning(
                    "GitHub discussion comments fetch failed for %s#%s",
                    repo,
                    number,
                    exc_info=True,
                )
                break

            if discussion is None or not _matches_labels(discussion, label_filter):
                break
            if not comments:
                break

            for comment in comments:
                if len(signals) >= limit or fetched_for_discussion >= self.max_comments_per_discussion:
                    break
                if not isinstance(comment, dict):
                    continue
                url = str(comment.get("url") or "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                signals.append(_to_signal(repo, discussion, comment, self.name))
                fetched_for_discussion += 1

            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
            if not after:
                break


def _to_signal(
    repo: str,
    discussion: dict[str, Any],
    comment: dict[str, Any],
    adapter_name: str,
) -> Signal:
    title = str(discussion.get("title") or "").strip() or f"{repo} discussion comment"
    body = str(comment.get("bodyText") or "").strip()
    author = comment.get("author") if isinstance(comment.get("author"), dict) else {}
    labels = _labels(discussion)
    category = discussion.get("category") if isinstance(discussion.get("category"), dict) else {}
    number = discussion.get("number")
    upvotes = _non_negative_int(comment.get("upvoteCount"), default=0)
    created_at = comment.get("createdAt")
    updated_at = comment.get("updatedAt")

    return Signal(
        id=_stable_id(repo, number, comment),
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=f"Comment on {title}",
        content=body[:4000] if body else title,
        url=str(comment.get("url") or ""),
        author=author.get("login") if isinstance(author, dict) else None,
        published_at=_parse_dt(created_at),
        tags=_build_tags(repo, title, body, labels, category),
        credibility=min(0.35 + (upvotes / 100), 1.0),
        metadata={
            "repository": repo,
            "discussion_number": number,
            "discussion_title": title,
            "discussion_url": discussion.get("url"),
            "comment_id": comment.get("id"),
            "category": category.get("name") if isinstance(category, dict) else None,
            "labels": labels[:10],
            "upvote_count": upvotes,
            "author": author.get("login") if isinstance(author, dict) else None,
            "created_at": created_at,
            "updated_at": updated_at,
            "signal_role": "problem",
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


def _discussion_number_map(value: object, repositories: list[str]) -> dict[str, list[int]]:
    if isinstance(value, dict):
        return {
            repo: _int_list(value.get(repo), [])
            for repo in repositories
            if _int_list(value.get(repo), [])
        }
    numbers = _int_list(value, [])
    return {repo: numbers for repo in repositories if numbers}


def _int_list(value: object, default: list[int]) -> list[int]:
    if value is None:
        values = list(default)
    elif isinstance(value, int) and not isinstance(value, bool):
        values = [value]
    elif isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return list(default)

    seen: set[int] = set()
    normalized: list[int] = []
    for item in values:
        if isinstance(item, bool):
            continue
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        normalized.append(number)
    return normalized


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _split_repo(repo: str) -> tuple[str, str]:
    owner, _, name = repo.partition("/")
    if not owner or not name or "/" in name:
        raise SourceParseError(
            f"Invalid GitHub repository name: {repo}",
            adapter_name="github_discussion_comments",
        )
    return owner, name


def _labels(discussion: dict[str, Any]) -> list[str]:
    labels = discussion.get("labels") or {}
    nodes = labels.get("nodes") if isinstance(labels, dict) else []
    if not isinstance(nodes, list):
        return []
    values: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        name = str(node.get("name") or "").strip()
        if name:
            values.append(name)
    return values


def _matches_labels(discussion: dict[str, Any], label_filter: set[str]) -> bool:
    if not label_filter:
        return True
    labels = {label.lower() for label in _labels(discussion)}
    return not labels.isdisjoint(label_filter)


def _build_tags(
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    category: dict[str, Any],
) -> list[str]:
    tags: set[str] = {"github", "discussion-comment"}
    category_name = str(category.get("name") or "").strip().lower()
    if category_name:
        tags.add(category_name)
    for label in labels:
        lower = label.lower()
        if lower in {"bug", "enhancement", "documentation", "security", "question"}:
            tags.add("docs" if lower == "documentation" else lower)

    text = " ".join([repo, title, body, " ".join(labels), category_name]).lower()
    keyword_map = {
        "ai": ["ai", "artificial intelligence", "openai", "anthropic"],
        "agent": ["agent", "agentic"],
        "llm": ["llm", "language model", "gpt", "claude"],
        "mcp": ["mcp", "model context protocol"],
        "security": ["security", "vulnerability", "cve"],
        "typescript": ["typescript", "javascript", "vercel/ai"],
        "python": ["python"],
        "feedback": ["pain", "issue", "problem", "request", "feedback"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)
    return sorted(tags)[:10]


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _non_negative_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return default


def _stable_id(repo: str, number: object, comment: dict[str, Any]) -> str:
    comment_id = comment.get("id") or comment.get("url")
    return f"github_discussion_comments:{repo}#{number}:{comment_id}"


def _graphql_error_message(errors: object) -> str:
    if not isinstance(errors, list):
        return "unknown error"
    messages = [
        str(error.get("message") or "").strip()
        for error in errors
        if isinstance(error, dict) and str(error.get("message") or "").strip()
    ]
    return "; ".join(messages) if messages else "unknown error"
