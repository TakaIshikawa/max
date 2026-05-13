"""GitLab milestones import adapter."""

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


class GitLabMilestonesImportAdapter(SourceAdapter):
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
        return "gitlab_milestones_import"

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
                milestones = await self._fetch_project(client, project=project, limit=project_limit)
                signals.extend(
                    _milestone_signal(item, project, self.name)
                    for item in milestones
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
        milestones: list[dict[str, Any]] = []
        page = 1
        while len(milestones) < limit:
            page_size = min(self.per_page, limit - len(milestones))
            body = await self._get(
                client,
                f"{self.api_url}/projects/{_encode_project(project)}/milestones",
                params=_params(self._config, page=page, per_page=page_size),
            )
            if not isinstance(body, list) or not body:
                break
            milestones.extend(item for item in body if isinstance(item, dict))
            if len(body) < page_size:
                break
            page += 1
        return milestones[:limit]

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
                    "User-Agent": "max-gitlab-milestones-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitLab milestones fetch failed for %s", url, exc_info=True)
            return []


GitLabMilestonesAdapter = GitLabMilestonesImportAdapter


def _milestone_signal(milestone: dict[str, Any], project: str, adapter_name: str) -> Signal:
    milestone_iid = _text(milestone.get("iid"))
    milestone_id = _text(milestone.get("id"))
    title = _text(milestone.get("title")) or f"GitLab milestone {milestone_iid or milestone_id}"
    state = _text(milestone.get("state"))
    counts = _counts(milestone)
    expired = _expired(milestone)
    return Signal(
        id=f"gitlab-milestone:{project}:{milestone_iid or milestone_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{project} {title}".strip(),
        content=_text(milestone.get("description")) or _content(title=title, state=state, counts=counts),
        url=_text(milestone.get("web_url")),
        author=None,
        published_at=_parse_dt(milestone.get("updated_at") or milestone.get("created_at")),
        tags=sorted({"gitlab", "milestone", state, "expired" if expired else ""} - {""})[:10],
        credibility=0.7,
        metadata={
            "signal_role": "readiness",
            "project_id": milestone.get("project_id"),
            "project_path": project,
            "milestone_id": milestone.get("id"),
            "milestone_iid": milestone.get("iid"),
            "id": milestone.get("id"),
            "iid": milestone.get("iid"),
            "title": title,
            "description": _text(milestone.get("description")) or None,
            "state": state or None,
            "due_date": milestone.get("due_date"),
            "start_date": milestone.get("start_date"),
            "web_url": milestone.get("web_url"),
            "counts": counts,
            "expired": expired,
            "created_at": milestone.get("created_at"),
            "updated_at": milestone.get("updated_at"),
            "raw": milestone,
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
        "search",
        "title",
        "updated_after",
        "updated_before",
        "include_parent_milestones",
    ):
        value = config.get(key)
        if key == "include_parent_milestones":
            bool_value = _bool(value)
            if bool_value is not None:
                params[key] = str(bool_value).lower()
            continue
        text = _optional(value)
        if text:
            params[key] = text
    return params


def _encode_project(project: str) -> str:
    return quote(unquote(str(project).strip()), safe="")


def _counts(milestone: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for key in ("issue_stats", "merge_requests_count"):
        value = milestone.get(key)
        if isinstance(value, dict):
            counts[key] = value
        elif value is not None:
            counts[key] = value
    for key in ("open_issues_count", "closed_issues_count"):
        if milestone.get(key) is not None:
            counts[key] = milestone.get(key)
    return counts


def _expired(milestone: dict[str, Any]) -> bool | None:
    value = milestone.get("expired")
    if isinstance(value, bool):
        return value
    return _bool(value)


def _content(*, title: str, state: str, counts: dict[str, Any]) -> str:
    parts = [f"GitLab milestone {title}"]
    if state:
        parts.append(f"state {state}")
    issue_stats = counts.get("issue_stats")
    if isinstance(issue_stats, dict):
        opened = issue_stats.get("opened")
        closed = issue_stats.get("closed")
        if opened is not None or closed is not None:
            parts.append(f"issues opened {opened or 0} closed {closed or 0}")
    return "; ".join(parts)


def _bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


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
    if isinstance(value, (str, int)) and not isinstance(value, bool):
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
