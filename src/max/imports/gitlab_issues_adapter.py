"""GitLab issues import adapter."""

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


class GitLabIssuesImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("token"))
                or os.getenv("GITLAB_PRIVATE_TOKEN")
                or os.getenv("GITLAB_TOKEN")
            )
        )
        self.api_url = _api_url(
            api_url
            or _optional(self._config.get("api_url"))
            or _optional(self._config.get("gitlab_url"))
            or _optional(self._config.get("base_url"))
            or os.getenv("GITLAB_API_URL")
            or GITLAB_API
        )
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_issues_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def projects(self) -> list[str]:
        return _strings(
            self._config.get("projects")
            or self._config.get("project_ids")
            or self._config.get("project_paths")
            or self._config.get("project_id")
            or self._config.get("project_path")
        )

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=20, maximum=100)

    @property
    def per_project_limit(self) -> int | None:
        value = self._config.get("per_project_limit")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.projects:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project in self.projects:
                if len(signals) >= limit:
                    break
                project_limit = min(self.per_project_limit or limit, limit - len(signals))
                issues = await self._fetch_project(client, project=project, limit=project_limit)
                signals.extend(
                    _issue_signal(item, project, self.name)
                    for item in issues
                    if isinstance(item, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project(
        self,
        client: httpx.AsyncClient,
        *,
        project: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        page = 1
        while len(issues) < limit:
            page_size = min(self.per_page, limit - len(issues))
            body = await self._get(
                client,
                f"{self.api_url}/projects/{_encode_project(project)}/issues",
                params=_params(self._config, page=page, per_page=page_size),
            )
            if not isinstance(body, list) or not body:
                break
            issues.extend(item for item in body if isinstance(item, dict))
            if len(body) < page_size:
                break
            page += 1
        return issues[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any],
    ) -> object:
        try:
            response = await client.get(
                url,
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-issues-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitLab issues fetch failed for %s", url, exc_info=True)
            return []


GitLabIssuesAdapter = GitLabIssuesImportAdapter


def _issue_signal(issue: dict[str, Any], project: str, adapter_name: str) -> Signal:
    issue_iid = _text(issue.get("iid"))
    issue_id = _text(issue.get("id"))
    title = _text(issue.get("title")) or f"GitLab issue {issue_iid or issue_id}"
    state = _text(issue.get("state"))
    labels = _strings(issue.get("labels"))
    milestone = issue.get("milestone") if isinstance(issue.get("milestone"), dict) else {}
    author = issue.get("author") if isinstance(issue.get("author"), dict) else {}
    assignees = issue.get("assignees") if isinstance(issue.get("assignees"), list) else []
    return Signal(
        id=f"gitlab-issue:{project}:{issue_iid or issue_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title,
        content=_text(issue.get("description"))[:4000],
        url=_text(issue.get("web_url")),
        author=_optional(author.get("username") or author.get("name")),
        published_at=_parse_dt(issue.get("created_at") or issue.get("updated_at")),
        tags=sorted({"gitlab", "issue", state, *labels} - {""})[:10],
        credibility=0.7,
        metadata={
            "signal_role": "readiness",
            "project_id": issue.get("project_id"),
            "project_path": project,
            "issue_iid": issue.get("iid"),
            "issue_id": issue.get("id"),
            "iid": issue.get("iid"),
            "id": issue.get("id"),
            "title": title,
            "description": _text(issue.get("description")) or None,
            "state": state or None,
            "labels": labels,
            "milestone": _summary(milestone),
            "assignees": [_summary(item) for item in assignees if isinstance(item, dict)],
            "author": _summary(author),
            "web_url": issue.get("web_url"),
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
            "closed_at": issue.get("closed_at"),
            "raw": issue,
        },
    )


def _api_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.endswith("/api/v4"):
        url = f"{url}/api/v4"
    return url


def _params(config: dict, *, page: int, per_page: int) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    for key in (
        "state",
        "labels",
        "milestone",
        "created_after",
        "created_before",
        "updated_after",
        "updated_before",
        "order_by",
        "sort",
    ):
        value = _optional(config.get(key))
        if value:
            params[key] = value
    return params


def _encode_project(project: str) -> str:
    return quote(unquote(str(project).strip()), safe="")


def _summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": value.get("id"),
        "iid": value.get("iid"),
        "username": _text(value.get("username")) or None,
        "name": _text(value.get("name")) or None,
        "title": _text(value.get("title")) or None,
        "state": _text(value.get("state")) or None,
        "web_url": value.get("web_url"),
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
        value = [item.strip() for item in value.split(",")]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, bool):
            continue
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
