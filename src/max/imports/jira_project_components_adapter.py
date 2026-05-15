"""Jira project components import adapter."""

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


class JiraProjectComponentsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        bearer_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.base_url = (base_url or _optional(self._config.get("base_url")) or os.getenv("JIRA_BASE_URL") or "").rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("JIRA_EMAIL") or os.getenv("JIRA_USERNAME"))
        self.api_token = api_token if api_token is not None else (_optional(self._config.get("api_token")) or os.getenv("JIRA_API_TOKEN"))
        self.bearer_token = bearer_token if bearer_token is not None else (_optional(self._config.get("bearer_token")) or os.getenv("JIRA_BEARER_TOKEN"))
        self._client = client

    @property
    def name(self) -> str:
        return "jira_project_components_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def project_keys(self) -> list[str]:
        return _strings(self._config.get("project_keys") or self._config.get("projects") or self._config.get("project_key"))

    @property
    def max_results(self) -> int:
        return _positive_int(self._config.get("max_results"), default=50, maximum=100)

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.email and self.api_token))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.base_url or not self.project_keys or not self._has_auth:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for project_key in self.project_keys:
                if len(signals) >= limit:
                    break
                components = await self._fetch_project_components(client, project_key=project_key, limit=limit - len(signals))
                for component in components:
                    signal = _component_signal(component, project_key, self.name, self.base_url, seen)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_components(self, client: httpx.AsyncClient, *, project_key: str, limit: int) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = []
        start_at = 0
        while len(components) < limit:
            body = await self._get(
                client,
                f"{self.base_url}/rest/api/3/project/{quote(project_key, safe='')}/component",
                params={"startAt": start_at, "maxResults": min(self.max_results, limit - len(components))},
            )
            page = _page_values(body)
            if not page:
                break
            components.extend(page)
            if isinstance(body, list):
                break
            total = _int(body.get("total")) if isinstance(body, dict) else 0
            start_at = _int(body.get("startAt")) + len(page) if isinstance(body, dict) else 0
            is_last = bool(body.get("isLast")) if isinstance(body, dict) else True
            if is_last or (total and start_at >= total):
                break
        return components[:limit]

    async def _get(self, client: httpx.AsyncClient, url: str, *, params: dict[str, Any]) -> object:
        headers = {"Accept": "application/json"}
        auth = None
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            auth = (self.email or "", self.api_token or "")
        try:
            response = await client.get(url, headers=headers, auth=auth, params=params)
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("Jira project component fetch failed for %s", url, exc_info=True)
            return {}


JiraProjectComponentAdapter = JiraProjectComponentsAdapter


def _component_signal(component: dict[str, Any], project_key: str, adapter_name: str, base_url: str, seen: set[str]) -> Signal | None:
    component_id = _optional(component.get("id"))
    name = _text(component.get("name"))
    if not component_id and not name:
        return None
    signal_id = f"jira-project-component:{project_key}:{component_id or name}"
    if signal_id in seen:
        return None
    seen.add(signal_id)
    lead = component.get("lead") if isinstance(component.get("lead"), dict) else {}
    lead_name = _text(lead.get("displayName") or lead.get("name"))
    description = _text(component.get("description"))
    archived = _bool_or_none(component.get("archived"))
    released = _bool_or_none(component.get("released"))
    assignee_type = _text(component.get("assigneeType") or component.get("realAssigneeType"))

    return Signal(
        id=signal_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=name or f"{project_key} component",
        content=_content(name=name, description=description, lead=lead_name, assignee_type=assignee_type, archived=archived, released=released, project_key=project_key),
        url=_text(component.get("self")) or base_url,
        author=lead_name or None,
        published_at=_parse_dt(component.get("created") or component.get("createdAt")),
        tags=sorted({"jira", "project-component", project_key, "archived" if archived else "", "released" if released else ""} - {""})[:10],
        credibility=0.7,
        metadata={
            "jira_component_id": component.get("id"),
            "project_key": project_key,
            "name": name or None,
            "description": description or None,
            "lead": lead,
            "lead_name": lead_name or None,
            "assignee_type": assignee_type or None,
            "archived": archived,
            "released": released,
            "self": component.get("self"),
            "raw": component,
        },
    )


def _content(*, name: str, description: str, lead: str, assignee_type: str, archived: bool | None, released: bool | None, project_key: str) -> str:
    parts = [f"Jira {project_key} component"]
    if name:
        parts.append(name)
    if description:
        parts.append(description)
    if lead:
        parts.append(f"lead {lead}")
    if assignee_type:
        parts.append(f"assignee type {assignee_type}")
    if archived is not None:
        parts.append(f"archived {archived}")
    if released is not None:
        parts.append(f"released {released}")
    return "; ".join(parts)


def _page_values(body: object) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict) and isinstance(body.get("values"), list):
        return [item for item in body["values"] if isinstance(item, dict)]
    return []


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


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
