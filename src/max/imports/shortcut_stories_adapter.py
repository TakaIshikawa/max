"""Shortcut story import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
SHORTCUT_API = "https://api.app.shortcut.com/api/v3"


class ShortcutStoriesAdapter(SourceAdapter):
    """Fetch Shortcut stories and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        workflow_state_id: str | int | None = None,
        project_id: str | int | None = None,
        epic_id: str | int | None = None,
        owner_id: str | None = None,
        label: str | None = None,
        archived: bool | None = None,
        page_size: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("token"))
                or _optional(self._config.get("api_token"))
                or os.getenv("SHORTCUT_API_TOKEN")
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or SHORTCUT_API).rstrip(
            "/"
        )
        self.workflow_state_id = (
            workflow_state_id
            if workflow_state_id is not None
            else self._config.get("workflow_state_id")
        )
        self.project_id = project_id if project_id is not None else self._config.get("project_id")
        self.epic_id = epic_id if epic_id is not None else self._config.get("epic_id")
        self.owner_id = owner_id if owner_id is not None else _optional(self._config.get("owner_id"))
        self.label = label if label is not None else _optional(self._config.get("label"))
        self.archived = archived if archived is not None else _optional_bool(self._config.get("archived"))
        self._page_size = page_size if page_size is not None else self._config.get("page_size")
        self._client = client

    @property
    def name(self) -> str:
        return "shortcut_stories_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def page_size(self) -> int:
        value = self._page_size
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return min(value, 100)
        return 25

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            stories = await self._fetch_stories(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        return [
            _story_signal(story, adapter_name=self.name)
            for story in stories[:limit]
            if isinstance(story, dict)
        ]

    async def _fetch_stories(
        self, client: httpx.AsyncClient, *, limit: int
    ) -> list[dict[str, Any]]:
        stories: list[dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        url = f"{self.api_url}/search/stories"
        params: dict[str, Any] | None = self._params(page=page, page_size=self.page_size)
        while len(stories) < limit and url:
            request_page_size = min(self.page_size, max(1, limit - len(stories)))
            if params is not None:
                params["page_size"] = request_page_size
            body = await self._get(client, url=url, params=params)
            page_items = _story_items(body)
            if not page_items:
                break
            for story in page_items:
                if not isinstance(story, dict):
                    continue
                story_id = _text(story.get("id"))
                if not story_id or story_id in seen:
                    continue
                seen.add(story_id)
                stories.append(story)
                if len(stories) >= limit:
                    break
            next_url = _next_url(body)
            if next_url:
                url = next_url
                params = None
            else:
                if len(page_items) < request_page_size:
                    break
                page += 1
                params = self._params(page=page, page_size=self.page_size)
        return stories

    def _params(self, *, page: int, page_size: int) -> dict[str, Any]:
        return {"query": self._query(), "page": page, "page_size": page_size}

    def _query(self) -> str:
        terms: list[str] = []
        if self.workflow_state_id not in (None, ""):
            terms.append(f"workflow_state_id:{self.workflow_state_id}")
        if self.project_id not in (None, ""):
            terms.append(f"project:{self.project_id}")
        if self.epic_id not in (None, ""):
            terms.append(f"epic:{self.epic_id}")
        if self.owner_id:
            terms.append(f"owner:{self.owner_id}")
        if self.label:
            terms.append(f'label:"{self.label}"')
        if self.archived is True:
            terms.append("is:archived")
        elif self.archived is False:
            terms.append("!is:archived")
        return " ".join(terms)

    async def _get(
        self, client: httpx.AsyncClient, *, url: str, params: dict[str, Any] | None
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/json",
                    "Shortcut-Token": self.token or "",
                    "User-Agent": "max-shortcut-stories-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Shortcut story fetch failed", exc_info=True)
            return {}
        if isinstance(body, list):
            return {"data": body}
        return body if isinstance(body, dict) else {}


ShortcutStoryAdapter = ShortcutStoriesAdapter


def _story_signal(story: dict[str, Any], *, adapter_name: str) -> Signal:
    story_id = _text(story.get("id"))
    labels = _labels(story.get("labels"))
    owner_ids = _owner_ids(story.get("owner_ids") or story.get("owners"))
    workflow_state_id = _object_id(story.get("workflow_state") or story.get("workflow_state_id"))
    project_id = _object_id(story.get("project") or story.get("project_id"))
    epic_id = _object_id(story.get("epic") or story.get("epic_id"))
    created_at = _parse_dt(story.get("created_at"))
    story_type = _text(story.get("story_type"))
    return Signal(
        id=f"shortcut-story:{story_id}" if story_id else "",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(story.get("name")) or story_id,
        content=_text(story.get("description"))[:1000],
        url=_text(story.get("app_url") or story.get("url")),
        author=owner_ids[0] if owner_ids else None,
        published_at=created_at,
        tags=sorted({"shortcut", story_type, *labels} - {""})[:10],
        credibility=0.6,
        metadata={
            "shortcut_story_id": story.get("id"),
            "story_id": story.get("id"),
            "app_url": story.get("app_url"),
            "workflow_state_id": workflow_state_id,
            "project_id": project_id,
            "epic_id": epic_id,
            "owner_ids": owner_ids,
            "labels": labels,
            "archived": story.get("archived"),
            "story_type": story.get("story_type"),
            "estimate": story.get("estimate"),
            "deadline": story.get("deadline"),
            "created_at": story.get("created_at"),
            "updated_at": story.get("updated_at"),
            "completed_at": story.get("completed_at"),
        },
    )


def _story_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("data", "stories", "results"):
        value = body.get(key)
        if isinstance(value, list):
            return value
    return []


def _next_url(body: dict[str, Any]) -> str | None:
    next_value = body.get("next")
    if isinstance(next_value, str) and next_value:
        return next_value
    pagination = body.get("pagination") if isinstance(body.get("pagination"), dict) else {}
    next_value = pagination.get("next")
    if isinstance(next_value, str) and next_value:
        return next_value
    return None


def _labels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        label = _text(item.get("name")) if isinstance(item, dict) else _text(item)
        if label:
            labels.append(label)
    return labels


def _owner_ids(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list):
        return []
    owner_ids: list[str] = []
    for item in value:
        if isinstance(item, dict):
            owner_id = _text(item.get("id") or item.get("uuid"))
        else:
            owner_id = _text(item)
        if owner_id:
            owner_ids.append(owner_id)
    return owner_ids


def _object_id(value: object) -> object:
    if isinstance(value, dict):
        return value.get("id")
    return value


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = _text(value).lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
