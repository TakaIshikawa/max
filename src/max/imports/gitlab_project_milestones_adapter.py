"""GitLab project milestones import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITLAB_API = "https://gitlab.com/api/v4"


class GitLabProjectMilestonesAdapter(SourceAdapter):
    """Import GitLab project milestones as roadmap signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        private_token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            private_token
            if private_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("private_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("GITLAB_PRIVATE_TOKEN")
                    or os.getenv("GITLAB_TOKEN")
                )
            )
        )
        self.api_url = _api_url(
            api_url
            or _optional(self._config.get("api_url"))
            or _optional(self._config.get("gitlab_url"))
            or os.getenv("GITLAB_API_URL")
            or GITLAB_API
        )
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_project_milestones_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def project_id(self) -> str:
        return (
            _optional(self._config.get("project_id"))
            or _optional(self._config.get("project_path"))
            or os.getenv("GITLAB_PROJECT_ID")
            or os.getenv("GITLAB_PROJECT_PATH")
            or ""
        )

    @property
    def state(self) -> str | None:
        return _optional(self._config.get("state"))

    @property
    def search(self) -> str | None:
        return _optional(self._config.get("search"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_id:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            milestones = await self._fetch_milestones(client, limit=limit)
            return [
                _milestone_signal(milestone, project_id=self.project_id, adapter_name=self.name)
                for milestone in milestones
                if isinstance(milestone, dict)
            ][:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_milestones(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        milestones: list[dict[str, Any]] = []
        page = 1
        while len(milestones) < limit:
            page_size = min(self.page_size, limit - len(milestones))
            page_milestones, next_page = await self._fetch_page(client, page=page, page_size=page_size)
            if not page_milestones:
                break
            milestones.extend(page_milestones[: limit - len(milestones)])
            if next_page:
                page = next_page
            elif len(page_milestones) < page_size:
                break
            else:
                page += 1
        return milestones[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int | None]:
        params: dict[str, Any] = {"page": page, "per_page": page_size}
        if self.state:
            params["state"] = self.state
        if self.search:
            params["search"] = self.search
        url = f"{self.api_url}/projects/{_encode_project(self.project_id)}/milestones"
        try:
            response = await client.get(
                url,
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-project-milestones-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitLab project milestones fetch failed for %s", self.project_id, exc_info=True)
            return [], None
        milestones = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return milestones, _next_page(response)


GitLabProjectMilestoneAdapter = GitLabProjectMilestonesAdapter


def _milestone_signal(
    milestone: dict[str, Any],
    *,
    project_id: str,
    adapter_name: str,
) -> Signal:
    milestone_id = _text(milestone.get("id") or milestone.get("iid"))
    title = _text(milestone.get("title")) or milestone_id or "GitLab milestone"
    state = _text(milestone.get("state")).lower()
    stats = _stats(milestone)
    return Signal(
        id=f"gitlab-project-milestone:{project_id}:{milestone_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title,
        content=_content(title=title, description=_text(milestone.get("description")), state=state, stats=stats),
        url=_text(milestone.get("web_url")),
        author=None,
        published_at=_parse_dt(milestone.get("created_at") or milestone.get("updated_at")),
        tags=sorted({"gitlab", "project-milestone", state} - {""})[:10],
        credibility=0.7,
        metadata={
            "gitlab_milestone_id": milestone.get("id"),
            "iid": milestone.get("iid"),
            "project_id": project_id,
            "title": title,
            "description": milestone.get("description"),
            "state": milestone.get("state"),
            "start_date": milestone.get("start_date"),
            "due_date": milestone.get("due_date"),
            "created_at": milestone.get("created_at"),
            "updated_at": milestone.get("updated_at"),
            "expired": milestone.get("expired"),
            "web_url": milestone.get("web_url"),
            "issue_stats": stats.get("issues"),
            "merge_request_stats": stats.get("merge_requests"),
            "raw": milestone,
        },
    )


def _content(*, title: str, description: str, state: str, stats: dict[str, Any]) -> str:
    parts = [f"GitLab milestone {title}"]
    if state:
        parts.append(f"state {state}")
    issues = stats.get("issues")
    if isinstance(issues, dict) and issues:
        parts.append(_stats_content("issues", issues))
    merge_requests = stats.get("merge_requests")
    if isinstance(merge_requests, dict) and merge_requests:
        parts.append(_stats_content("merge requests", merge_requests))
    if description:
        parts.append(description)
    return "; ".join(part for part in parts if part)[:1000]


def _stats(milestone: dict[str, Any]) -> dict[str, Any]:
    stats = milestone.get("stats") if isinstance(milestone.get("stats"), dict) else {}
    return {
        "issues": _summary(stats.get("issue_stats"), ("total", "closed")),
        "merge_requests": _summary(stats.get("merge_requests_stats"), ("total", "closed", "merged")),
    }


def _stats_content(label: str, stats: dict[str, Any]) -> str:
    values = [f"{key} {value}" for key, value in stats.items() if value is not None]
    return f"{label}: {', '.join(values)}" if values else ""


def _api_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.endswith("/api/v4"):
        url = f"{url}/api/v4"
    return url


def _encode_project(project: str) -> str:
    return quote(unquote(str(project).strip()), safe="")


def _next_page(response: httpx.Response) -> int | None:
    value = _optional(response.headers.get("X-Next-Page"))
    if not value:
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number > 0 else None


def _summary(value: object, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: value.get(key) for key in keys if value.get(key) is not None}


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
