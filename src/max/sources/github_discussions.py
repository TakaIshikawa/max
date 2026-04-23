"""GitHub Discussions source adapter -- discussion threads from repositories."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

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

_DEFAULT_REPOSITORIES = [
    "modelcontextprotocol/servers",
    "langchain-ai/langchain",
    "openai/openai-python",
    "anthropics/anthropic-sdk-python",
    "vercel/ai",
]

_DISCUSSIONS_QUERY = """
query RepositoryDiscussions($owner: String!, $name: String!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    discussions(first: $first, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number
        title
        bodyText
        url
        createdAt
        updatedAt
        upvoteCount
        answerChosenAt
        category {
          name
          slug
        }
        author {
          login
        }
        comments {
          totalCount
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""


class GitHubDiscussionsAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "github_discussions"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def repositories(self) -> list[str]:
        return _string_list(self._config.get("repositories"), _DEFAULT_REPOSITORIES)

    @property
    def categories(self) -> list[str]:
        return _string_list(self._config.get("categories"), [])

    @property
    def labels(self) -> list[str]:
        return _string_list(self._config.get("labels"), [])

    @property
    def search_terms(self) -> list[str]:
        terms = _string_list(self._config.get("search_terms"), [])
        watchlist_terms = _string_list(self._config.get("watchlist_terms"), [])
        return _dedupe_strings(terms + watchlist_terms)

    @property
    def include_answered(self) -> bool:
        return bool(self._config.get("include_answered", True))

    @property
    def max_age_days(self) -> int | None:
        value = self._config.get("max_age_days")
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        try:
            days = int(value)
        except (TypeError, ValueError):
            return None
        return days if days > 0 else None

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

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_discussions")
    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        repo: str,
        *,
        first: int,
        after: str | None,
    ) -> tuple[list[dict], dict]:
        """Fetch one GraphQL page of discussions for a repository."""
        owner, name = _split_repo(repo)
        try:
            resp = await client.post(
                f"{GITHUB_API}/graphql",
                json={
                    "query": _DISCUSSIONS_QUERY,
                    "variables": {
                        "owner": owner,
                        "name": name,
                        "first": first,
                        "after": after,
                    },
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429 or _is_github_rate_limit(e.response):
                retry_after = e.response.headers.get("Retry-After")
                retry_seconds = float(retry_after) if retry_after else None
                raise SourceRateLimitError(
                    f"Rate limit exceeded for discussions: {repo}",
                    adapter_name=self.name,
                    retry_after=retry_seconds,
                ) from e
            if status in (401, 403):
                raise SourceAuthError(
                    f"Authentication failed (HTTP {status}) for discussions: {repo}",
                    adapter_name=self.name,
                ) from e
            if 500 <= status < 600:
                raise SourceTransientError(
                    f"Server error (HTTP {status}) for discussions: {repo}",
                    adapter_name=self.name,
                ) from e
            raise SourceTransientError(
                f"HTTP {status} for discussions: {repo}",
                adapter_name=self.name,
            ) from e
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse discussions response for: {repo}",
                adapter_name=self.name,
            ) from e

        if not isinstance(payload, dict):
            raise SourceParseError(
                f"Unexpected discussions response for: {repo}",
                adapter_name=self.name,
            )

        errors = payload.get("errors") or []
        if errors:
            _raise_graphql_error(errors, repo, self.name)

        discussions = (
            payload.get("data", {})
            .get("repository", {})
            .get("discussions", {})
        )
        if not isinstance(discussions, dict):
            raise SourceParseError(
                f"Unexpected discussions payload for: {repo}",
                adapter_name=self.name,
            )

        nodes = discussions.get("nodes") or []
        page_info = discussions.get("pageInfo") or {}
        if not isinstance(nodes, list) or not isinstance(page_info, dict):
            raise SourceParseError(
                f"Unexpected discussions page for: {repo}",
                adapter_name=self.name,
            )

        return nodes, page_info

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        per_page = min(max(limit, 1), 100)

        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        categories = {value.lower() for value in self.categories}
        text_terms = [value.lower() for value in self.search_terms + self.labels]
        cutoff = _cutoff(self.max_age_days)

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for repo in self.repositories:
                if len(signals) >= limit:
                    break

                after: str | None = None
                while len(signals) < limit:
                    try:
                        nodes, page_info = await self._fetch_page(
                            client,
                            repo,
                            first=per_page,
                            after=after,
                        )
                    except (SourceRateLimitError, SourceAuthError):
                        raise
                    except (
                        SourceTransientError,
                        SourceParseError,
                        httpx.RequestError,
                        httpx.TimeoutException,
                    ):
                        logger.warning(
                            "GitHub discussions fetch failed for repo: %s",
                            repo,
                            exc_info=True,
                        )
                        break

                    if not nodes:
                        break

                    for discussion in nodes:
                        if len(signals) >= limit:
                            break
                        if not isinstance(discussion, dict):
                            continue
                        if not _matches_filters(
                            discussion,
                            categories=categories,
                            text_terms=text_terms,
                            include_answered=self.include_answered,
                            cutoff=cutoff,
                        ):
                            continue

                        html_url = discussion.get("url", "")
                        if not html_url or html_url in seen_urls:
                            continue
                        seen_urls.add(html_url)

                        signals.append(_to_signal(repo, discussion, self.name))

                    if not page_info.get("hasNextPage"):
                        break
                    after = page_info.get("endCursor")
                    if not after:
                        break

        return signals[:limit]


def _string_list(value: object, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return list(default)
    return _dedupe_strings(item.strip() for item in values if isinstance(item, str) and item.strip())


def _dedupe_strings(values: object) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _split_repo(repo: str) -> tuple[str, str]:
    owner, _, name = repo.partition("/")
    if not owner or not name or "/" in name:
        raise SourceParseError(
            f"Invalid GitHub repository name: {repo}",
            adapter_name="github_discussions",
        )
    return owner, name


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cutoff(max_age_days: int | None) -> datetime | None:
    if max_age_days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _matches_filters(
    discussion: dict,
    *,
    categories: set[str],
    text_terms: list[str],
    include_answered: bool,
    cutoff: datetime | None,
) -> bool:
    answered = _is_answered(discussion)
    if answered and not include_answered:
        return False

    updated_at = _parse_dt(discussion.get("updatedAt"))
    created_at = _parse_dt(discussion.get("createdAt"))
    recency_dt = updated_at or created_at
    if cutoff is not None and recency_dt is not None and recency_dt < cutoff:
        return False

    category = discussion.get("category") or {}
    category_values = {
        str(category.get("name") or "").lower(),
        str(category.get("slug") or "").lower(),
    }
    if categories and categories.isdisjoint(category_values):
        return False

    text = " ".join(
        str(part or "")
        for part in [
            discussion.get("title"),
            discussion.get("bodyText"),
            category.get("name"),
            category.get("slug"),
        ]
    ).lower()
    return not text_terms or any(term in text for term in text_terms)


def _to_signal(repo: str, discussion: dict, adapter_name: str) -> Signal:
    title = str(discussion.get("title") or "").strip() or repo
    body = str(discussion.get("bodyText") or "").strip()
    category = discussion.get("category") or {}
    author = discussion.get("author") or {}
    created_at = discussion.get("createdAt")
    updated_at = discussion.get("updatedAt")
    upvote_count = _int_value(discussion.get("upvoteCount"))
    comment_count = _connection_count(discussion.get("comments"))
    answered = _is_answered(discussion)
    answer_count = _connection_count(discussion.get("answers"))
    if answer_count == 0 and answered:
        answer_count = 1

    return Signal(
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=title,
        content=body[:4000] if body else title,
        url=str(discussion.get("url") or ""),
        author=author.get("login") if isinstance(author, dict) else None,
        published_at=_parse_dt(created_at),
        tags=_build_tags(repo, discussion),
        credibility=_credibility(upvote_count, comment_count, answer_count, answered),
        metadata={
            "repository": repo,
            "discussion_number": discussion.get("number"),
            "category": category.get("name") if isinstance(category, dict) else None,
            "answer_count": answer_count,
            "comment_count": comment_count,
            "upvote_count": upvote_count,
            "author": author.get("login") if isinstance(author, dict) else None,
            "created_at": created_at,
            "updated_at": updated_at,
            "answered": answered,
        },
    )


def _connection_count(value: object) -> int:
    if isinstance(value, dict):
        return _int_value(value.get("totalCount"))
    return 0


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_answered(discussion: dict) -> bool:
    return bool(discussion.get("answerChosenAt"))


def _build_tags(repo: str, discussion: dict) -> list[str]:
    tags: set[str] = {"github", "discussion"}
    category = discussion.get("category") or {}
    category_name = str(category.get("name") or "").strip().lower()
    if category_name:
        tags.add(category_name)

    text = " ".join(
        str(part or "")
        for part in [
            repo,
            discussion.get("title"),
            discussion.get("bodyText"),
            category.get("name"),
        ]
    ).lower()
    keyword_map = {
        "ai": ["ai", "artificial intelligence", "openai", "anthropic"],
        "agent": ["agent", "agentic"],
        "llm": ["llm", "language model", "gpt", "claude"],
        "mcp": ["mcp", "model context protocol"],
        "security": ["security", "vulnerability", "cve"],
        "typescript": ["typescript", "javascript", "vercel/ai"],
        "python": ["python"],
        "devtools": ["cli", "developer tool", "sdk"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)

    return sorted(tags)[:10]


def _credibility(
    upvote_count: int,
    comment_count: int,
    answer_count: int,
    answered: bool,
) -> float:
    engagement = upvote_count + comment_count + answer_count
    answered_bonus = 0.1 if answered else 0.0
    return min(0.35 + answered_bonus + (engagement / 100), 1.0)


def _raise_graphql_error(errors: list, repo: str, adapter_name: str) -> None:
    message = "; ".join(
        str(error.get("message", "")) for error in errors if isinstance(error, dict)
    ).strip()
    lower = message.lower()
    if "rate limit" in lower:
        raise SourceRateLimitError(
            f"Rate limit exceeded for discussions: {repo}",
            adapter_name=adapter_name,
        )
    if "bad credentials" in lower or "resource not accessible" in lower or "unauthorized" in lower:
        raise SourceAuthError(
            f"Authentication failed for discussions: {repo}",
            adapter_name=adapter_name,
        )
    raise SourceTransientError(
        f"GraphQL error for discussions: {repo}: {message or 'unknown error'}",
        adapter_name=adapter_name,
    )


def _is_github_rate_limit(response: httpx.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    return response.status_code == 403 and remaining == "0"
