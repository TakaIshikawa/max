"""Sentry project releases import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
SENTRY_API = "https://sentry.io/api/0"


class SentryProjectReleasesAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        auth_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            auth_token
            if auth_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("auth_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("SENTRY_AUTH_TOKEN")
                )
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or SENTRY_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "sentry_project_releases_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def organization_slug(self) -> str | None:
        return _optional(self._config.get("organization_slug") or self._config.get("org"))

    @property
    def project_slugs(self) -> list[str]:
        return _strings(
            self._config.get("project_slugs")
            or self._config.get("projects")
            or self._config.get("project_slug")
        )

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=25, maximum=100)

    @property
    def per_project_limit(self) -> int | None:
        value = self._config.get("per_project_limit")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.organization_slug or not self.project_slugs:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project_slug in self.project_slugs:
                if len(signals) >= limit:
                    break
                project_limit = min(self.per_project_limit or limit, limit - len(signals))
                releases = await self._fetch_project_releases(client, project_slug=project_slug, limit=project_limit)
                signals.extend(
                    _release_signal(release, project_slug=project_slug, adapter_name=self.name)
                    for release in releases
                    if isinstance(release, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_releases(
        self,
        client: httpx.AsyncClient,
        *,
        project_slug: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        releases: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(releases) < limit:
            page_size = min(self.page_size, limit - len(releases))
            page_releases, cursor = await self._fetch_page(
                client,
                project_slug=project_slug,
                cursor=cursor,
                page_size=page_size,
            )
            if not page_releases:
                break
            releases.extend(page_releases[: limit - len(releases)])
            if not cursor:
                break
        return releases[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project_slug: str,
        cursor: str | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"per_page": page_size}
        if cursor:
            params["cursor"] = cursor
        for source, target in (("query", "query"), ("status", "status")):
            value = _optional(self._config.get(source))
            if value:
                params[target] = value
        url = f"{self.api_url}/projects/{self.organization_slug}/{project_slug}/releases/"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-project-releases-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Sentry releases fetch failed for project %s", project_slug, exc_info=True)
            return [], None
        releases = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return releases, _next_cursor(response)


SentryProjectReleaseAdapter = SentryProjectReleasesAdapter


def _release_signal(release: dict[str, Any], *, project_slug: str, adapter_name: str) -> Signal:
    version = _text(release.get("version")) or _text(release.get("shortVersion")) or _text(release.get("id"))
    owner = release.get("owner") if isinstance(release.get("owner"), dict) else {}
    user = release.get("user") if isinstance(release.get("user"), dict) else {}
    author = _optional(
        owner.get("name")
        or owner.get("username")
        or owner.get("email")
        or user.get("name")
        or user.get("username")
        or user.get("email")
    )
    commit_count = _int(release.get("commitCount") or release.get("commit_count"))
    return Signal(
        id=f"sentry-release:{project_slug}:{version}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{project_slug} release {version}".strip(),
        content=_content(release, version=version, commit_count=commit_count),
        url=_text(release.get("url") or release.get("permalink")),
        author=author,
        published_at=_parse_dt(release.get("dateReleased") or release.get("dateCreated")),
        tags=sorted({"sentry", "release", project_slug, _text(release.get("status"))} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "problem",
            "sentry_project_slug": project_slug,
            "sentry_release_id": release.get("id"),
            "version": version or None,
            "short_version": release.get("shortVersion"),
            "status": release.get("status"),
            "date_created": release.get("dateCreated"),
            "date_released": release.get("dateReleased"),
            "commit_count": commit_count,
            "last_commit": _summary_dict(release.get("lastCommit")),
            "last_deploy": _summary_dict(release.get("lastDeploy")),
            "new_groups": _int(release.get("newGroups")),
            "projects": release.get("projects") if isinstance(release.get("projects"), list) else [],
            "owner": _user_summary(owner),
            "user": _user_summary(user),
            "url": release.get("url") or release.get("permalink"),
            "raw": release,
        },
    )


def _content(release: dict[str, Any], *, version: str, commit_count: int) -> str:
    parts = [f"Sentry release {version or 'unknown'}"]
    if release.get("dateReleased"):
        parts.append(f"released {release['dateReleased']}")
    elif release.get("dateCreated"):
        parts.append(f"created {release['dateCreated']}")
    if commit_count:
        parts.append(f"{commit_count} commits")
    return "; ".join(parts)


def _next_cursor(response: httpx.Response) -> str | None:
    next_link = response.links.get("next") if response.links else None
    if not next_link:
        return None
    if _text(next_link.get("results")).lower() == "false":
        return None
    cursor = _optional(next_link.get("cursor"))
    if cursor:
        return cursor
    next_url = _optional(next_link.get("url"))
    if not next_url:
        return None
    return _optional(str(httpx.URL(next_url).params.get("cursor")))


def _user_summary(user: dict[str, Any]) -> dict[str, Any]:
    return {
        key: user.get(key)
        for key in ("id", "name", "username", "email")
        if user.get(key) is not None
    }


def _summary_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
