"""GitLab releases import adapter."""

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


class GitLabReleasesImportAdapter(SourceAdapter):
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
        return "gitlab_releases_import"

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
                project_limit = min(
                    self.per_project_limit or limit,
                    limit - len(signals),
                )
                releases = await self._fetch_project(
                    client,
                    project=project,
                    limit=project_limit,
                )
                signals.extend(
                    _release_signal(item, project, self.name)
                    for item in releases
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
        releases: list[dict[str, Any]] = []
        page = 1
        while len(releases) < limit:
            page_size = min(self.per_page, limit - len(releases))
            body = await self._get(
                client,
                f"{self.api_url}/projects/{_encode_project(project)}/releases",
                params=_params(self._config, page=page, per_page=page_size),
            )
            if not isinstance(body, list) or not body:
                break
            releases.extend(item for item in body if isinstance(item, dict))
            if len(body) < page_size:
                break
            page += 1
        return releases[:limit]

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
                    "User-Agent": "max-gitlab-releases-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitLab releases fetch failed for %s", url, exc_info=True)
            return []


GitLabReleasesAdapter = GitLabReleasesImportAdapter


def _release_signal(release: dict[str, Any], project: str, adapter_name: str) -> Signal:
    tag_name = _text(release.get("tag_name"))
    name = _text(release.get("name"))
    title = f"{project} {name or tag_name}".strip()
    if name and tag_name and name != tag_name:
        title = f"{project} {name} ({tag_name})"
    author = release.get("author") if isinstance(release.get("author"), dict) else {}
    return Signal(
        id=f"gitlab-release:{project}:{tag_name or _text(release.get('name'))}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title or f"{project} release",
        content=_text(release.get("description"))[:4000],
        url=_release_url(release),
        author=_optional(author.get("username") or author.get("name")),
        published_at=_parse_dt(release.get("released_at") or release.get("created_at")),
        tags=sorted({"gitlab", "release", tag_name} - {""})[:10],
        credibility=0.7,
        metadata={
            "signal_role": "readiness",
            "project_id": release.get("project_id"),
            "project_path": project,
            "tag_name": tag_name or None,
            "name": name or None,
            "description": _text(release.get("description")) or None,
            "author": _summary(author),
            "released_at": release.get("released_at"),
            "created_at": release.get("created_at"),
            "commit": _summary_dict(release.get("commit")),
            "tag_path": _tag_path(release),
            "commit_path": _commit_path(release.get("commit")),
            "milestones": _milestone_titles(release.get("milestones")),
            "assets_links": _assets_links(release.get("assets")),
            "assets_count": _assets_count(release.get("assets")),
            "raw": release,
        },
    )


def _api_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.endswith("/api/v4"):
        url = f"{url}/api/v4"
    return url


def _params(config: dict, *, page: int, per_page: int) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    for source, target in (
        ("released_after", "released_after"),
        ("released_before", "released_before"),
        ("order_by", "order_by"),
        ("sort", "sort"),
    ):
        value = _optional(config.get(source))
        if value:
            params[target] = value
    return params


def _encode_project(project: str) -> str:
    return quote(unquote(str(project).strip()), safe="")


def _release_url(release: dict[str, Any]) -> str:
    links = release.get("_links")
    if isinstance(links, dict):
        self_url = _text(links.get("self"))
        if self_url:
            return self_url
    return _text(release.get("url")) or _text(release.get("web_url"))


def _tag_path(release: dict[str, Any]) -> str | None:
    links = release.get("_links")
    if isinstance(links, dict):
        return _optional(links.get("edit_url") or links.get("closed_issues_url"))
    return None


def _commit_path(commit: object) -> str | None:
    if not isinstance(commit, dict):
        return None
    return _optional(commit.get("web_url") or commit.get("id"))


def _summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": value.get("id"),
        "username": _text(value.get("username")) or None,
        "name": _text(value.get("name")) or None,
        "web_url": value.get("web_url"),
    }


def _summary_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _milestone_titles(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    titles: list[str] = []
    for item in value:
        if isinstance(item, dict):
            title = _text(item.get("title"))
            if title:
                titles.append(title)
        elif isinstance(item, str) and item.strip():
            titles.append(item.strip())
    return titles[:10]


def _assets_links(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    links = value.get("links")
    if not isinstance(links, list):
        return []
    return [item for item in links if isinstance(item, dict)]


def _assets_count(value: object) -> int:
    if not isinstance(value, dict):
        return 0
    total = 0
    for key in ("links", "sources"):
        items = value.get(key)
        if isinstance(items, list):
            total += len(items)
    return total


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
