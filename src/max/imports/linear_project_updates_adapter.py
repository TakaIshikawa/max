"""Linear project updates import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"


class LinearProjectUpdatesAdapter(SourceAdapter):
    """Fetch Linear project updates and convert them to roadmap signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("LINEAR_API_KEY"))
        self.api_url = api_url or _optional(self._config.get("api_url")) or LINEAR_GRAPHQL_URL
        self._client = client

    @property
    def name(self) -> str:
        return "linear_project_updates_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def project_ids(self) -> list[str]:
        return _strings(self._config.get("project_ids") or self._config.get("project_id"))

    @property
    def health(self) -> list[str]:
        return _strings(self._config.get("health") or self._config.get("healthes"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=50, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, _positive_int(self._config.get("limit"), default=limit, maximum=100000))
        if effective_limit <= 0 or not self.token or not self.project_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for project_id in self.project_ids:
                if len(signals) >= effective_limit:
                    break
                updates = await self._fetch_project_updates(client, project_id=project_id, limit=effective_limit - len(signals))
                for update in updates:
                    signal = _update_signal(update, project_id=project_id, adapter_name=self.name, seen=seen)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= effective_limit:
                        break
            return signals
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_updates(self, client: httpx.AsyncClient, *, project_id: str, limit: int) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(updates) < limit:
            page_size = min(self.page_size, limit - len(updates))
            body = await self._post(client, project_id=project_id, first=page_size, after=cursor)
            nodes, cursor, has_next_page = _updates_page(body)
            if not nodes:
                break
            updates.extend(nodes[: limit - len(updates)])
            if not has_next_page:
                break
        return updates[:limit]

    async def _post(self, client: httpx.AsyncClient, *, project_id: str, first: int, after: str | None) -> dict[str, Any]:
        try:
            response = await client.post(
                self.api_url,
                json={
                    "query": PROJECT_UPDATES_QUERY,
                    "variables": {
                        "projectId": project_id,
                        "first": first,
                        "after": after,
                        "filter": self._filter(),
                    },
                },
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "User-Agent": "max-linear-project-updates-import/1",
                },
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Linear project update fetch failed for project %s", project_id, exc_info=True)
            return {}
        if not isinstance(body, dict) or body.get("errors"):
            if isinstance(body, dict) and body.get("errors"):
                logger.warning("Linear project update fetch returned GraphQL errors: %s", body.get("errors"))
            return {}
        return body

    def _filter(self) -> dict[str, Any] | None:
        if not self.health:
            return None
        if len(self.health) == 1:
            return {"health": {"eq": self.health[0]}}
        return {"or": [{"health": {"eq": value}} for value in self.health]}


LinearProjectUpdateAdapter = LinearProjectUpdatesAdapter


PROJECT_UPDATES_QUERY = """
query MaxLinearProjectUpdates($projectId: String!, $first: Int!, $after: String, $filter: ProjectUpdateFilter) {
  project(id: $projectId) {
    id
    name
    url
    updates(first: $first, after: $after, filter: $filter, orderBy: createdAt) {
      nodes {
        id
        body
        health
        url
        createdAt
        updatedAt
        user { id name displayName email url }
        project { id name url }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def _updates_page(body: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None, bool]:
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    updates = project.get("updates") if isinstance(project.get("updates"), dict) else {}
    nodes = updates.get("nodes")
    page_info = updates.get("pageInfo") if isinstance(updates.get("pageInfo"), dict) else {}
    return (
        [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else [],
        _optional(page_info.get("endCursor")),
        bool(page_info.get("hasNextPage")),
    )


def _update_signal(update: dict[str, Any], *, project_id: str, adapter_name: str, seen: set[str]) -> Signal | None:
    update_id = _optional(update.get("id"))
    if not update_id or update_id in seen:
        return None
    seen.add(update_id)
    project = update.get("project") if isinstance(update.get("project"), dict) else {}
    user = update.get("user") if isinstance(update.get("user"), dict) else {}
    project_name = _optional(project.get("name")) or project_id
    health = _optional(update.get("health"))
    author = _optional(user.get("displayName")) or _optional(user.get("name")) or _optional(user.get("email"))
    return Signal(
        id=f"linear-project-update:{update_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{project_name} project update{f' {health}' if health else ''}",
        content=_text(update.get("body"))[:1000],
        url=_optional(update.get("url")) or _optional(project.get("url")) or "",
        author=author,
        published_at=_parse_dt(update.get("createdAt")),
        tags=sorted({"linear", "project-update", health or ""} - {""})[:10],
        credibility=0.66,
        metadata={
            "linear_project_update_id": update_id,
            "linear_project_id": project.get("id") or project_id,
            "project_id": project.get("id") or project_id,
            "project_name": project_name,
            "project_url": project.get("url"),
            "health": health,
            "body": _text(update.get("body")),
            "author": {
                "id": user.get("id"),
                "name": user.get("name") or user.get("displayName"),
                "display_name": user.get("displayName"),
                "email": user.get("email"),
                "url": user.get("url"),
            },
            "created_at": update.get("createdAt"),
            "updated_at": update.get("updatedAt"),
            "raw": update,
        },
    )


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
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
