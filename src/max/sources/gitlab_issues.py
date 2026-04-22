"""GitLab Issues source adapter — public issue tracker pain points."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from urllib.parse import quote

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

GITLAB_API = "https://gitlab.com/api/v4"

_DEFAULT_QUERIES = [
    "ai agent",
    "llm",
    "mcp server",
    "machine learning",
]


class GitLabIssuesAdapter(SourceAdapter):
    """Search public GitLab issues and normalize them into forum signals."""

    @property
    def name(self) -> str:
        return "gitlab_issues"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def labels(self) -> list[str]:
        return self._configured_terms("labels", [])

    @property
    def project_ids(self) -> list[str]:
        values = self._config.get("project_ids", [])
        project_ids: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, (str, int)) or isinstance(value, bool):
                continue
            project_id = str(value).strip()
            if not project_id or project_id in seen:
                continue
            seen.add(project_id)
            project_ids.append(project_id)
        return project_ids

    @property
    def state(self) -> str:
        state = self._config.get("state", "opened")
        return state if isinstance(state, str) and state else "opened"

    @property
    def min_upvotes(self) -> int:
        value = self._config.get("min_upvotes", 0)
        if isinstance(value, bool):
            return 0
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="gitlab_issues")
    async def _fetch_issues(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        per_query: int,
        project_id: str | None = None,
    ) -> list[dict]:
        url = _issues_url(project_id)
        params: dict[str, object] = {
            "search": query,
            "scope": "all",
            "state": self.state,
            "order_by": "upvotes",
            "sort": "desc",
            "per_page": per_query,
        }
        if self.labels:
            params["labels"] = ",".join(self.labels)

        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError("GitLab issues response was not a list")
            return data
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                retry_after = e.response.headers.get("Retry-After")
                retry_seconds = float(retry_after) if retry_after else None
                raise SourceRateLimitError(
                    f"Rate limit exceeded for GitLab issues query: {query}",
                    adapter_name=self.name,
                    retry_after=retry_seconds,
                ) from e
            if status in (401, 403):
                raise SourceAuthError(
                    f"Authentication failed (HTTP {status}) for GitLab issues query: {query}",
                    adapter_name=self.name,
                ) from e
            raise SourceTransientError(
                f"HTTP {status} for GitLab issues query: {query}",
                adapter_name=self.name,
            ) from e
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse GitLab issues response for query: {query}",
                adapter_name=self.name,
            ) from e

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        query_scopes = [(query, project_id) for query in self.queries for project_id in self._scopes()]
        if not query_scopes:
            return []

        per_query = max(limit // len(query_scopes), 5)
        headers = {"Accept": "application/json"}
        token = os.environ.get("GITLAB_TOKEN")
        if token:
            headers["PRIVATE-TOKEN"] = token

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for query, project_id in query_scopes:
                if len(signals) >= limit:
                    break

                try:
                    issues = await self._fetch_issues(
                        client,
                        query=query,
                        per_query=per_query,
                        project_id=project_id,
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
                        "GitLab issues search failed for query=%s project_id=%s",
                        query,
                        project_id,
                        exc_info=True,
                    )
                    continue

                self._append_issue_signals(
                    signals,
                    issues,
                    limit=limit,
                    seen_urls=seen_urls,
                    search_query=query,
                )

        return signals[:limit]

    def _scopes(self) -> list[str | None]:
        project_ids = self.project_ids
        return project_ids if project_ids else [None]

    def _append_issue_signals(
        self,
        signals: list[Signal],
        issues: list[dict],
        *,
        limit: int,
        seen_urls: set[str],
        search_query: str,
    ) -> None:
        for issue in issues:
            if len(signals) >= limit:
                break

            upvotes = _int_value(issue.get("upvotes"))
            if upvotes < self.min_upvotes:
                continue

            url = str(issue.get("web_url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            labels = _labels(issue.get("labels"))
            comments_count = _int_value(
                issue.get("user_notes_count", issue.get("comments_count"))
            )
            title = str(issue.get("title") or "")
            description = str(issue.get("description") or "")
            project_id = issue.get("project_id")
            issue_iid = issue.get("iid")

            signals.append(
                Signal(
                    source_type=SignalSourceType.FORUM,
                    source_adapter=self.name,
                    title=title,
                    content=description[:1000] if description else title,
                    url=url,
                    author=_author(issue.get("author")),
                    published_at=_parse_dt(issue.get("created_at")),
                    tags=_build_tags(labels, title),
                    credibility=min((upvotes + comments_count) / 100, 1.0),
                    metadata={
                        "project_id": project_id,
                        "issue_iid": issue_iid,
                        "labels": labels[:10],
                        "state": issue.get("state"),
                        "upvotes": upvotes,
                        "comments_count": comments_count,
                        "search_query": search_query,
                    },
                )
            )


def _issues_url(project_id: str | None) -> str:
    if project_id:
        return f"{GITLAB_API}/projects/{quote(project_id, safe='')}/issues"
    return f"{GITLAB_API}/issues"


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _labels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            labels.append(item)
    return labels


def _author(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    author = value.get("username") or value.get("name")
    return author if isinstance(author, str) and author else None


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _build_tags(labels: list[str], title: str) -> list[str]:
    tags: set[str] = {label.lower() for label in labels[:10] if label}
    title_lower = title.lower()
    keyword_map = {
        "ai": ["ai", "artificial intelligence"],
        "agent": ["agent", "agentic"],
        "llm": ["llm", "language model"],
        "mcp": ["mcp", "model context protocol"],
        "security": ["security", "vulnerability", "cve"],
        "performance": ["performance", "slow", "latency"],
        "bug": ["bug", "error", "failure"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in title_lower for keyword in keywords):
            tags.add(tag)
    tags.add("gitlab")
    return sorted(tags)[:10]
