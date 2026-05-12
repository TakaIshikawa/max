"""GitLab project hooks import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITLAB_API = "https://gitlab.com/api/v4"
EVENT_FLAG_KEYS = (
    "push_events",
    "issues_events",
    "confidential_issues_events",
    "merge_requests_events",
    "tag_push_events",
    "note_events",
    "confidential_note_events",
    "job_events",
    "pipeline_events",
    "wiki_page_events",
    "deployment_events",
    "releases_events",
    "emoji_events",
)


class GitLabProjectHooksAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        project_id: str | None = None,
        api_url: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("GITLAB_TOKEN"))
        self.project_id = project_id if project_id is not None else (
            _optional(self._config.get("project_id"))
            or _optional(self._config.get("project_path"))
            or os.getenv("GITLAB_PROJECT_ID")
            or os.getenv("GITLAB_PROJECT_PATH")
        )
        configured_url = (
            api_url
            or base_url
            or _optional(self._config.get("api_url"))
            or _optional(self._config.get("base_url"))
            or os.getenv("GITLAB_API_URL")
            or GITLAB_API
        )
        self.api_url = configured_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_project_hooks_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_id:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            hooks = await self._fetch_hooks(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for hook in hooks:
            if not isinstance(hook, dict):
                continue
            signals.append(_hook_signal(hook, self.project_id, self.name))
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_hooks(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        hooks: list[dict[str, Any]] = []
        page = 1
        while len(hooks) < limit:
            page_size = min(self.per_page, limit - len(hooks))
            body = await self._get(client, page=page, per_page=page_size)
            if not isinstance(body, list) or not body:
                break
            hooks.extend(item for item in body if isinstance(item, dict))
            if len(body) < page_size:
                break
            page += 1
        return hooks[:limit]

    async def _get(self, client: httpx.AsyncClient, *, page: int, per_page: int) -> object:
        try:
            response = await client.get(
                self._endpoint,
                params={"page": page, "per_page": per_page},
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-project-hooks-import/1",
                },
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitLab project hooks fetch failed for %s", self._endpoint, exc_info=True)
            return []

    @property
    def _endpoint(self) -> str:
        project = quote(self.project_id or "", safe="")
        return f"{self.api_url}/projects/{project}/hooks"


GitLabProjectHookAdapter = GitLabProjectHooksAdapter


def _hook_signal(hook: dict[str, Any], project_id: str, adapter_name: str) -> Signal:
    hook_id = _text(hook.get("id"))
    url = _text(hook.get("url"))
    events = _event_flags(hook)
    enabled_events = [key for key, enabled in events.items() if enabled is True]
    disabled_events = [key for key, enabled in events.items() if enabled is False]
    created_at = hook.get("created_at")
    alert_status = _alert_status(hook)
    status_label = _text(alert_status.get("alert_status") or alert_status.get("disabled_until") or "")
    return Signal(
        id=f"gitlab-project-hook:{project_id}:{hook_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"GitLab project hook {hook_id}",
        content=_content(url=url, enabled_events=enabled_events, branch_filter=_text(hook.get("push_events_branch_filter"))),
        url=url,
        author=None,
        published_at=_parse_dt(created_at),
        tags=sorted({"gitlab", "project-hook", "webhook", status_label, *enabled_events} - {""})[:10],
        credibility=0.7,
        metadata={
            "gitlab_project_hook_id": hook.get("id"),
            "hook_id": hook.get("id"),
            "project_id": project_id,
            "url": hook.get("url"),
            "event_flags": events,
            "enabled_events": enabled_events,
            "disabled_events": disabled_events,
            "push_events_branch_filter": hook.get("push_events_branch_filter"),
            "created_at": created_at,
            **alert_status,
            "raw": hook,
        },
    )


def _content(*, url: str, enabled_events: list[str], branch_filter: str) -> str:
    parts = [f"GitLab project hook for {url or 'configured webhook'}"]
    if enabled_events:
        parts.append(f"events {', '.join(enabled_events)}")
    else:
        parts.append("no enabled events")
    if branch_filter:
        parts.append(f"branch filter {branch_filter}")
    return "; ".join(parts)


def _event_flags(hook: dict[str, Any]) -> dict[str, bool | None]:
    flags: dict[str, bool | None] = {}
    for key in EVENT_FLAG_KEYS:
        if key in hook:
            flags[key] = bool(hook.get(key))
    return flags


def _alert_status(hook: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in ("alert_status", "disabled_until", "last_response", "recent_failures", "enable_ssl_verification"):
        if key in hook:
            fields[key] = hook.get(key)
    return fields


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
