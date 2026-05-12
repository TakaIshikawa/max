"""GitHub issue timeline events import adapter."""

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


class GitHubIssueTimelineEventsAdapter(SourceAdapter):
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
        return "github_issue_timeline_events_import"

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
            events: list[tuple[int, dict[str, Any]]] = []
            for issue_number in self.issue_numbers:
                if len(events) >= limit:
                    break
                issue_events = await self._fetch_issue_events(
                    client,
                    issue_number=issue_number,
                    limit=limit - len(events),
                )
                if issue_events is None:
                    return []
                events.extend((issue_number, event) for event in issue_events)
        finally:
            if close_client:
                await client.aclose()

        repository = f"{self.owner}/{self.repo}"
        return [
            _timeline_event_signal(event, repository, issue_number, self.name)
            for issue_number, event in events[:limit]
            if isinstance(event, dict)
        ]

    async def _fetch_issue_events(
        self,
        client: httpx.AsyncClient,
        *,
        issue_number: int,
        limit: int,
    ) -> list[dict[str, Any]] | None:
        events: list[dict[str, Any]] = []
        page = 1
        while len(events) < limit:
            page_size = min(self.per_page, limit - len(events))
            page_events = await self._fetch_page(
                client,
                issue_number=issue_number,
                page=page,
                page_size=page_size,
            )
            if page_events is None:
                return None
            if not page_events:
                break
            events.extend(page_events)
            if len(page_events) < page_size:
                break
            page += 1
        return events[:limit]

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
                f"{self.api_url}/repos/{self.owner}/{self.repo}/issues/{issue_number}/timeline",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "max-github-issue-timeline-events-import/1",
                },
                params=self._params(page=page, page_size=page_size),
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub issue timeline events fetch failed", exc_info=True)
            return None
        return [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []

    def _params(self, *, page: int, page_size: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "per_page": page_size}
        since = _optional(self._config.get("since"))
        if since:
            params["since"] = since
        return params


GitHubIssueTimelineEventAdapter = GitHubIssueTimelineEventsAdapter


def _timeline_event_signal(
    event: dict[str, Any],
    repository: str,
    issue_number: int,
    adapter_name: str,
) -> Signal:
    actor = event.get("actor") if isinstance(event.get("actor"), dict) else {}
    author = _optional(actor.get("login") or actor.get("name") or actor.get("email"))
    event_type = _text(event.get("event")) or "timeline_event"
    event_id = _event_id(event, repository, issue_number, event_type, author)
    created_at = event.get("created_at")
    content = _event_content(event, event_type)
    return Signal(
        id=f"github-issue-timeline-event:{repository}:{issue_number}:{event_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{repository} issue #{issue_number} {event_type.replace('_', ' ')}",
        content=content[:1000],
        url=_event_url(event),
        author=author,
        published_at=_parse_dt(created_at),
        tags=sorted({"github", "issue", "timeline-event", event_type} - {""})[:10],
        credibility=0.65,
        metadata={
            "github_issue_timeline_event_id": event.get("id"),
            "node_id": event.get("node_id"),
            "repository": repository,
            "issue_number": issue_number,
            "event": event.get("event"),
            "actor": {
                "login": actor.get("login"),
                "id": actor.get("id"),
                "node_id": actor.get("node_id"),
                "type": actor.get("type"),
                "html_url": actor.get("html_url"),
            },
            "created_at": event.get("created_at"),
            "updated_at": event.get("updated_at"),
            "url": event.get("url"),
            "html_url": event.get("html_url"),
            "issue_url": event.get("issue_url"),
            "commit_url": event.get("commit_url"),
            "label": event.get("label"),
            "assignee": event.get("assignee"),
            "assigner": event.get("assigner"),
            "source": event.get("source"),
            "raw": event,
        },
    )


def _event_id(
    event: dict[str, Any],
    repository: str,
    issue_number: int,
    event_type: str,
    author: str | None,
) -> str:
    explicit = _text(event.get("id") or event.get("node_id"))
    if explicit:
        return explicit
    parts = [
        repository,
        str(issue_number),
        event_type,
        _text(event.get("created_at")),
        author or "",
        _text(event.get("url") or event.get("html_url")),
    ]
    return ":".join(parts)


def _event_content(event: dict[str, Any], event_type: str) -> str:
    for key in ("body", "commit_id"):
        value = _optional(event.get(key))
        if value:
            return value
    label = event.get("label") if isinstance(event.get("label"), dict) else {}
    label_name = _optional(label.get("name"))
    if label_name:
        return f"{event_type.replace('_', ' ')} label {label_name}"
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    source_issue = source.get("issue") if isinstance(source.get("issue"), dict) else {}
    source_title = _optional(source_issue.get("title"))
    if source_title:
        return source_title
    return event_type.replace("_", " ")


def _event_url(event: dict[str, Any]) -> str:
    html_url = _optional(event.get("html_url"))
    if html_url:
        return html_url
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    source_issue = source.get("issue") if isinstance(source.get("issue"), dict) else {}
    return _text(source_issue.get("html_url") or event.get("url") or event.get("issue_url"))


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
    elif isinstance(value, (int, float)):
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
