"""GitHub releases import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"
VALID_STATES = {"published", "draft", "prerelease"}


class GitHubReleasesImportAdapter(SourceAdapter):
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
            else (_optional(self._config.get("token")) or os.getenv("GITHUB_TOKEN"))
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or GITHUB_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "github_releases_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def repositories(self) -> list[str]:
        return _strings(self._config.get("repositories") or self._config.get("repos"))

    @property
    def state(self) -> str | None:
        state = (_optional(self._config.get("state")) or "").lower()
        return state if state in VALID_STATES else None

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.repositories:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for repository in self.repositories:
                if len(signals) >= limit:
                    break
                owner_repo = _owner_repo(repository)
                if not owner_repo:
                    continue
                releases = await self._fetch_repository(
                    client, repository=owner_repo, limit=limit - len(signals)
                )
                signals.extend(
                    _release_signal(item, owner_repo, self.name)
                    for item in releases
                    if isinstance(item, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        *,
        repository: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        releases: list[dict[str, Any]] = []
        page = 1
        while len(releases) < limit:
            page_size = min(self.per_page, limit - len(releases))
            body = await self._get(
                client,
                f"{self.api_url}/repos/{repository}/releases",
                params={"per_page": page_size, "page": page},
            )
            if not isinstance(body, list) or not body:
                break
            filtered = [item for item in body if isinstance(item, dict) and _matches_state(item, self.state)]
            releases.extend(filtered)
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
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "max-github-releases-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitHub releases fetch failed for %s", url, exc_info=True)
            return []


GitHubReleasesAdapter = GitHubReleasesImportAdapter


def _release_signal(release: dict[str, Any], repository: str, adapter_name: str) -> Signal:
    author = release.get("author") if isinstance(release.get("author"), dict) else {}
    assets = release.get("assets") if isinstance(release.get("assets"), list) else []
    tag_name = _text(release.get("tag_name"))
    title = _text(release.get("name")) or tag_name or f"{repository} release"
    draft = bool(release.get("draft"))
    prerelease = bool(release.get("prerelease"))
    state = "draft" if draft else "prerelease" if prerelease else "published"
    return Signal(
        id=f"github-release:{repository}:{_text(release.get('id')) or tag_name}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title,
        content=_text(release.get("body"))[:1000],
        url=_text(release.get("html_url")),
        author=_text(author.get("login")) or None,
        published_at=_parse_dt(release.get("published_at") or release.get("created_at")),
        tags=sorted({"github", "release", state, tag_name} - {""})[:10],
        credibility=0.7,
        metadata={
            "github_release_id": release.get("id"),
            "repository": repository,
            "tag_name": tag_name,
            "name": _text(release.get("name")) or None,
            "draft": draft,
            "prerelease": prerelease,
            "state": state,
            "author": _summary(author),
            "assets_count": len(assets),
            "target_commitish": release.get("target_commitish"),
            "created_at": release.get("created_at"),
            "published_at": release.get("published_at"),
            "html_url": release.get("html_url"),
            "upload_url": release.get("upload_url"),
        },
    )


def _matches_state(release: dict[str, Any], state: str | None) -> bool:
    if state is None:
        return True
    if state == "draft":
        return bool(release.get("draft"))
    if state == "prerelease":
        return bool(release.get("prerelease"))
    return not bool(release.get("draft")) and not bool(release.get("prerelease"))


def _owner_repo(value: str) -> str | None:
    text = value.strip()
    if "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    return f"{owner}/{repo}" if owner and repo else None


def _summary(value: dict[str, Any]) -> dict[str, Any]:
    return {"login": value.get("login"), "id": value.get("id"), "html_url": value.get("html_url")}


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
