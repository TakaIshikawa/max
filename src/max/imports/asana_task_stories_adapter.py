"""Asana task stories import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
ASANA_API = "https://app.asana.com/api/1.0"
OPT_FIELDS = ",".join(
    [
        "gid",
        "type",
        "resource_subtype",
        "text",
        "html_text",
        "created_at",
        "created_by.gid",
        "created_by.name",
        "created_by.email",
        "author.gid",
        "author.name",
        "author.email",
        "permalink_url",
        "target.gid",
        "target.name",
    ]
)


class AsanaTaskStoriesAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        access_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            access_token
            if access_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("access_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("ASANA_ACCESS_TOKEN")
                )
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or ASANA_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "asana_task_stories_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def task_gids(self) -> list[str]:
        return _task_gids(
            self._config.get("task_gids")
            or self._config.get("tasks")
            or self._config.get("task_gid")
        )

    @property
    def workspace_gid(self) -> str | None:
        return _optional(self._config.get("workspace_gid"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("limit"), default=30, maximum=100)

    @property
    def per_task_limit(self) -> int | None:
        value = self._config.get("per_task_limit")
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @property
    def include_html_text(self) -> bool:
        return bool(self._config.get("include_html_text"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.task_gids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for task_gid in self.task_gids:
                if len(signals) >= limit:
                    break
                task_limit = limit - len(signals)
                if self.per_task_limit:
                    task_limit = min(task_limit, self.per_task_limit)
                stories = await self._fetch_task_stories(
                    client,
                    task_gid=task_gid,
                    limit=task_limit,
                )
                for story in stories:
                    if not _is_comment_like(story):
                        continue
                    signals.append(
                        _story_signal(
                            story,
                            task_gid=task_gid,
                            adapter_name=self.name,
                            include_html_text=self.include_html_text,
                        )
                    )
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_task_stories(
        self,
        client: httpx.AsyncClient,
        *,
        task_gid: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        stories: list[dict[str, Any]] = []
        offset: str | None = None
        while len(stories) < limit:
            page_size = min(self.page_size, limit - len(stories))
            page_stories, offset = await self._fetch_page(
                client,
                task_gid=task_gid,
                offset=offset,
                page_size=page_size,
            )
            if not page_stories:
                break
            stories.extend(page_stories[: limit - len(stories)])
            if not offset or len(page_stories) < page_size:
                break
        return stories[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        task_gid: str,
        offset: str | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {
            "limit": page_size,
            "opt_fields": OPT_FIELDS,
        }
        if offset:
            params["offset"] = offset
        if self.workspace_gid:
            params["workspace"] = self.workspace_gid
        url = f"{self.api_url}/tasks/{task_gid}/stories"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-asana-task-stories-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Asana task stories fetch failed for task %s", task_gid, exc_info=True)
            return [], None
        data = body.get("data") if isinstance(body, dict) else None
        stories = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        return stories, _next_offset(body)


AsanaTaskStoryAdapter = AsanaTaskStoriesAdapter


def _story_signal(
    story: dict[str, Any],
    *,
    task_gid: str,
    adapter_name: str,
    include_html_text: bool,
) -> Signal:
    author = story.get("created_by") if isinstance(story.get("created_by"), dict) else {}
    if not author:
        author = story.get("author") if isinstance(story.get("author"), dict) else {}
    target = story.get("target") if isinstance(story.get("target"), dict) else {}
    story_gid = _text(story.get("gid"))
    story_type = _text(story.get("type"))
    resource_subtype = _text(story.get("resource_subtype"))
    content = _text(story.get("text"))
    title = f"Asana task {task_gid} story"
    if resource_subtype:
        title = f"Asana task {task_gid} {resource_subtype.replace('_', ' ')}"
    metadata: dict[str, Any] = {
        "asana_task_gid": task_gid,
        "asana_story_gid": story.get("gid"),
        "story_type": story.get("type"),
        "resource_subtype": story.get("resource_subtype"),
        "author": _author_summary(author),
        "created_at": story.get("created_at"),
        "permalink_url": story.get("permalink_url"),
        "text": content,
        "target": {
            "gid": target.get("gid"),
            "name": target.get("name"),
        },
        "raw": story,
    }
    if include_html_text:
        metadata["html_text"] = story.get("html_text")
    return Signal(
        id=f"asana-task-story:{task_gid}:{story_gid}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title,
        content=content[:1000],
        url=_text(story.get("permalink_url")),
        author=_optional(author.get("name") or author.get("email")),
        published_at=_parse_dt(story.get("created_at")),
        tags=sorted({"asana", "task-story", story_type, resource_subtype} - {""})[:10],
        credibility=0.6,
        metadata=metadata,
    )


def _is_comment_like(story: dict[str, Any]) -> bool:
    story_type = _text(story.get("type")).lower()
    resource_subtype = _text(story.get("resource_subtype")).lower()
    return story_type == "comment" or resource_subtype in {"comment_added", "comment_deleted", "comment"}


def _author_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {"gid": value.get("gid"), "name": value.get("name"), "email": value.get("email")}


def _next_offset(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    next_page = body.get("next_page")
    if not isinstance(next_page, dict):
        return None
    return _optional(next_page.get("offset"))


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


def _task_gids(value: object) -> list[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    gids: list[str] = []
    for item in value:
        if isinstance(item, dict):
            gid = _text(item.get("gid") or item.get("task_gid") or item.get("id"))
        else:
            gid = _text(item)
        if gid:
            gids.append(gid)
    return gids


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
