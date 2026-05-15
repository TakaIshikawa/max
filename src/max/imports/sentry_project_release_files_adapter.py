"""Sentry project release files import adapter."""

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
SENTRY_API = "https://sentry.io/api/0"


class SentryProjectReleaseFilesAdapter(SourceAdapter):
    """Fetch Sentry release artifacts/files for configured projects and releases."""

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
        return "sentry_project_release_files_import"

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
    def release_versions(self) -> list[str]:
        return _strings(
            self._config.get("release_versions")
            or self._config.get("releases")
            or self._config.get("release_version")
            or self._config.get("version")
        )

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("per_page"),
            default=25,
            maximum=100,
        )

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if (
            limit <= 0
            or not self.token
            or not self.organization_slug
            or not self.project_slugs
            or not self.release_versions
        ):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project_slug in self.project_slugs:
                for release_version in self.release_versions:
                    if len(signals) >= limit:
                        break
                    files = await self._fetch_release_files(
                        client,
                        project_slug=project_slug,
                        release_version=release_version,
                        limit=limit - len(signals),
                    )
                    signals.extend(
                        _file_signal(
                            artifact,
                            organization_slug=self.organization_slug,
                            project_slug=project_slug,
                            release_version=release_version,
                            adapter_name=self.name,
                        )
                        for artifact in files
                        if isinstance(artifact, dict)
                    )
                if len(signals) >= limit:
                    break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_release_files(
        self,
        client: httpx.AsyncClient,
        *,
        project_slug: str,
        release_version: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(files) < limit:
            page_size = min(self.page_size, limit - len(files))
            page_files, cursor = await self._fetch_page(
                client,
                project_slug=project_slug,
                release_version=release_version,
                cursor=cursor,
                page_size=page_size,
            )
            if not page_files:
                break
            files.extend(page_files[: limit - len(files)])
            if not cursor:
                break
        return files[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project_slug: str,
        release_version: str,
        cursor: str | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"per_page": page_size}
        if cursor:
            params["cursor"] = cursor
        version = quote(release_version, safe="")
        url = f"{self.api_url}/projects/{self.organization_slug}/{project_slug}/releases/{version}/files/"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-project-release-files-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning(
                "Sentry release files fetch failed for project %s release %s",
                project_slug,
                release_version,
                exc_info=True,
            )
            return [], None
        files = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return files, _next_cursor(response)


SentryProjectReleaseFileAdapter = SentryProjectReleaseFilesAdapter


def _file_signal(
    artifact: dict[str, Any],
    *,
    organization_slug: str,
    project_slug: str,
    release_version: str,
    adapter_name: str,
) -> Signal:
    file_id = _optional(artifact.get("id") or artifact.get("fileId"))
    name = _optional(artifact.get("name") or artifact.get("filename") or artifact.get("fileName"))
    stable = file_id or name or _hash(artifact) or "unknown"
    created_at = _optional(artifact.get("dateCreated") or artifact.get("createdAt") or artifact.get("created_at"))
    dist = _optional(artifact.get("dist"))
    size = _int(artifact.get("size") or artifact.get("sizeBytes") or artifact.get("size_bytes"))
    sha = _optional(artifact.get("sha1") or artifact.get("sha") or artifact.get("checksum") or artifact.get("hash"))
    headers = artifact.get("headers") if isinstance(artifact.get("headers"), dict) else {}
    return Signal(
        id=f"sentry-release-file:{organization_slug}:{project_slug}:{release_version}:{stable}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{project_slug} release {release_version} file {name or stable}",
        content=_content(
            project_slug=project_slug,
            release_version=release_version,
            name=name or stable,
            dist=dist,
            size=size,
            sha=sha,
            created_at=created_at,
            headers=headers,
        ),
        url=_text(artifact.get("url") or artifact.get("downloadUrl") or artifact.get("download_url")),
        author=None,
        published_at=_parse_dt(created_at),
        tags=sorted({"sentry", "release", "artifact", project_slug, dist or ""} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "problem",
            "sentry_organization_slug": organization_slug,
            "sentry_project_slug": project_slug,
            "release_version": release_version,
            "file_id": file_id,
            "file_name": name,
            "dist": dist,
            "size": size,
            "sha": sha,
            "headers": headers,
            "date_created": created_at,
            "url": artifact.get("url") or artifact.get("downloadUrl") or artifact.get("download_url"),
            "raw": artifact,
        },
    )


def _content(
    *,
    project_slug: str,
    release_version: str,
    name: str,
    dist: str | None,
    size: int,
    sha: str | None,
    created_at: str | None,
    headers: dict[str, Any],
) -> str:
    parts = [f"Sentry {project_slug} release {release_version} file {name}"]
    if dist:
        parts.append(f"dist {dist}")
    if size:
        parts.append(f"{size} bytes")
    if sha:
        parts.append(f"sha {sha}")
    if headers:
        parts.append(f"{len(headers)} headers")
    if created_at:
        parts.append(f"created {created_at}")
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


def _hash(artifact: dict[str, Any]) -> str | None:
    return _optional(artifact.get("sha1") or artifact.get("sha") or artifact.get("checksum") or artifact.get("hash"))


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
