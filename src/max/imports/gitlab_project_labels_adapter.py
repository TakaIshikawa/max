"""GitLab project labels import adapter."""

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


class GitLabProjectLabelsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        gitlab_url: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("private_token"))
                or _optional(self._config.get("bearer_token"))
                or _optional(self._config.get("token"))
                or os.getenv("GITLAB_PRIVATE_TOKEN")
                or os.getenv("GITLAB_BEARER_TOKEN")
                or os.getenv("GITLAB_TOKEN")
            )
        )
        configured_url = (
            api_url
            or _optional(self._config.get("api_url"))
            or gitlab_url
            or _optional(self._config.get("gitlab_url"))
            or os.getenv("GITLAB_API_URL")
            or GITLAB_API
        )
        self.api_url = _api_url(configured_url)
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_project_labels_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def project_ids(self) -> list[str]:
        return _strings(
            self._config.get("project_ids")
            or self._config.get("project_paths")
            or self._config.get("projects")
            or self._config.get("project_id")
            or self._config.get("project_path")
            or self._config.get("project")
        )

    @property
    def per_page(self) -> int:
        return _positive_int(
            self._config.get("per_page") or self._config.get("page_size"),
            default=30,
            maximum=100,
        )

    @property
    def use_bearer_token(self) -> bool:
        auth_type = _text(
            self._config.get("auth_type")
            or self._config.get("auth_scheme")
            or self._config.get("token_type")
        ).lower()
        return bool(self._config.get("bearer_token")) or auth_type in {"bearer", "oauth", "oauth2"}

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rows: list[tuple[str, dict[str, Any]]] = []
            for project_id in self.project_ids:
                if len(rows) >= limit:
                    break
                labels = await self._fetch_project_labels(
                    client,
                    project_id=project_id,
                    limit=limit - len(rows),
                )
                if labels is None:
                    return []
                rows.extend((project_id, label) for label in labels)
            return [_label_signal(project_id, label, self.name, self.api_url) for project_id, label in rows[:limit]]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_labels(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        limit: int,
    ) -> list[dict[str, Any]] | None:
        labels: list[dict[str, Any]] = []
        page = 1
        while len(labels) < limit:
            page_size = min(self.per_page, limit - len(labels))
            body, next_page = await self._fetch_page(
                client,
                project_id=project_id,
                page=page,
                page_size=page_size,
            )
            if body is None:
                return None
            if not body:
                break
            labels.extend(body)
            if not next_page and len(body) < page_size:
                break
            page = next_page or page + 1
        return labels[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]] | None, int | None]:
        url = f"{self.api_url}/projects/{quote(project_id, safe='')}/labels"
        try:
            response = await client.get(
                url,
                headers=self._headers(),
                params={"page": page, "per_page": page_size},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitLab project labels fetch failed for %s", project_id, exc_info=True)
            return None, None
        if not isinstance(body, list):
            return None, None
        next_page = _positive_int(response.headers.get("X-Next-Page"), default=0, maximum=1_000_000) or None
        return [item for item in body if isinstance(item, dict)], next_page

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "max-gitlab-project-labels-import/1",
        }
        if self.use_bearer_token:
            headers["Authorization"] = f"Bearer {self.token or ''}"
        else:
            headers["PRIVATE-TOKEN"] = self.token or ""
        return headers


GitLabProjectLabelAdapter = GitLabProjectLabelsAdapter


def _label_signal(
    project_id: str,
    label: dict[str, Any],
    adapter_name: str,
    api_url: str,
) -> Signal:
    name = _text(label.get("name"))
    label_id = _text(label.get("id")) or name
    description = _text(label.get("description"))
    color = _text(label.get("color"))
    priority = label.get("priority")
    open_count = _int(label.get("open_issues_count"))
    closed_count = _int(label.get("closed_issues_count"))
    title = name or f"GitLab project {project_id} label"
    return Signal(
        id=f"gitlab-label:{project_id}:{label_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title,
        content=_content(title, description, color, priority, open_count, closed_count)[:1000],
        url=_text(label.get("web_url") or label.get("url")) or _label_url(api_url, project_id, name),
        author=None,
        published_at=_parse_dt(label.get("created_at") or label.get("updated_at")),
        tags=sorted({"gitlab", "label", name} - {""})[:10],
        credibility=0.65,
        metadata={
            "project_id": project_id,
            "label_id": label.get("id"),
            "name": name,
            "color": label.get("color"),
            "text_color": label.get("text_color"),
            "description": label.get("description"),
            "priority": priority,
            "open_issues_count": open_count,
            "closed_issues_count": closed_count,
            "subscribed": label.get("subscribed"),
            "is_project_label": label.get("is_project_label"),
            "created_at": label.get("created_at"),
            "updated_at": label.get("updated_at"),
            "raw": label,
        },
    )


def _content(
    title: str,
    description: str,
    color: str,
    priority: object,
    open_count: int,
    closed_count: int,
) -> str:
    parts = [description or f"GitLab label {title}"]
    if color:
        parts.append(f"color {color}")
    if priority is not None:
        parts.append(f"priority {priority}")
    parts.append(f"{open_count} open issues")
    parts.append(f"{closed_count} closed issues")
    return "; ".join(parts)


def _api_url(value: str) -> str:
    url = value.rstrip("/")
    return f"{url}/api/v4" if not url.endswith("/api/v4") else url


def _label_url(api_url: str, project_id: str, name: str) -> str:
    base = api_url.removesuffix("/api/v4")
    if not base or not name:
        return ""
    project_path = "/".join(quote(part, safe="") for part in project_id.split("/"))
    return f"{base}/{project_path}/-/labels?search={quote(name)}"


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


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
