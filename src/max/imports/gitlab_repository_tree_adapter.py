"""GitLab repository tree import adapter."""

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


class GitLabRepositoryTreeAdapter(SourceAdapter):
    """Fetch GitLab repository tree entries and convert them to Max signals."""

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
        return "gitlab_repository_tree_import"

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
            or self._config.get("project")
        )

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page") or self._config.get("page_size"), default=100, maximum=100)

    @property
    def ref(self) -> str | None:
        return _optional(self._config.get("ref"))

    @property
    def path(self) -> str | None:
        return _optional(self._config.get("path"))

    @property
    def recursive(self) -> bool | None:
        if "recursive" not in self._config:
            return None
        return _bool(self._config.get("recursive"), default=False)

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
                entries = await self._fetch_project(client, project=project, limit=limit - len(signals))
                signals.extend(_tree_signal(entry, project, self.name, ref=self.ref, filter_path=self.path) for entry in entries)
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
        entries: list[dict[str, Any]] = []
        page = 1
        while len(entries) < limit:
            page_size = min(self.per_page, limit - len(entries))
            body = await self._get(
                client,
                f"{self.api_url}/projects/{_encode_project(project)}/repository/tree",
                params=_params(page=page, per_page=page_size, path=self.path, ref=self.ref, recursive=self.recursive),
            )
            if not isinstance(body, list) or not body:
                break
            entries.extend(item for item in body if isinstance(item, dict))
            if len(body) < page_size:
                break
            page += 1
        return entries[:limit]

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
                    "User-Agent": "max-gitlab-repository-tree-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitLab repository tree fetch failed for %s", url, exc_info=True)
            return []


GitLabRepositoryTreeImportAdapter = GitLabRepositoryTreeAdapter


def _tree_signal(
    entry: dict[str, Any],
    project: str,
    adapter_name: str,
    *,
    ref: str | None,
    filter_path: str | None,
) -> Signal:
    entry_path = _text(entry.get("path"))
    name = _text(entry.get("name")) or entry_path.rsplit("/", 1)[-1]
    entry_type = _text(entry.get("type"))
    entry_id = _text(entry.get("id")) or f"{entry_type}:{entry_path}"
    return Signal(
        id=f"gitlab-repository-tree:{project}:{entry_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{project} {entry_type or 'tree'} {entry_path or name}".strip(),
        content=_content(project=project, path=entry_path, entry_type=entry_type, mode=_text(entry.get("mode"))),
        url=_text(entry.get("web_url") or entry.get("url")),
        author=None,
        published_at=_parse_dt(entry.get("created_at") or entry.get("updated_at")),
        tags=sorted({"gitlab", "repository-tree", entry_type, name} - {""})[:10],
        credibility=0.65,
        metadata={
            "signal_role": "implementation",
            "project_id": project,
            "project_path": project,
            "path": entry_path or None,
            "name": name or None,
            "type": entry.get("type"),
            "mode": entry.get("mode"),
            "id": entry.get("id"),
            "ref": ref,
            "filter_path": filter_path,
            "url": entry.get("web_url") or entry.get("url"),
            "raw": entry,
        },
    )


def _api_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.endswith("/api/v4"):
        url = f"{url}/api/v4"
    return url


def _params(*, page: int, per_page: int, path: str | None, ref: str | None, recursive: bool | None) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if path:
        params["path"] = path
    if ref:
        params["ref"] = ref
    if recursive is not None:
        params["recursive"] = str(recursive).lower()
    return params


def _encode_project(project: str) -> str:
    return quote(unquote(str(project).strip()), safe="")


def _content(*, project: str, path: str, entry_type: str, mode: str) -> str:
    parts = [f"GitLab repository tree entry for {project}"]
    if path:
        parts.append(path)
    if entry_type:
        parts.append(entry_type)
    if mode:
        parts.append(f"mode {mode}")
    return "; ".join(parts)


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


def _bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
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
