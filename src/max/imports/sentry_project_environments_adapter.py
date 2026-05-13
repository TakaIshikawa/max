"""Sentry project environments import adapter."""

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


class SentryProjectEnvironmentsAdapter(SourceAdapter):
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
        return "sentry_project_environments_import"

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
                environments = await self._fetch_project_environments(client, project_slug=project_slug, limit=project_limit)
                signals.extend(
                    _environment_signal(
                        environment,
                        organization_slug=self.organization_slug or "",
                        project_slug=project_slug,
                        adapter_name=self.name,
                    )
                    for environment in environments
                    if isinstance(environment, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_environments(
        self,
        client: httpx.AsyncClient,
        *,
        project_slug: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        environments: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(environments) < limit:
            page_size = min(self.page_size, limit - len(environments))
            page_environments, cursor = await self._fetch_page(
                client,
                project_slug=project_slug,
                cursor=cursor,
                page_size=page_size,
            )
            if not page_environments:
                break
            environments.extend(page_environments[: limit - len(environments)])
            if not cursor:
                break
        return environments[:limit]

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
        for source, target in (("visibility", "visibility"), ("name", "name")):
            value = _optional(self._config.get(source))
            if value:
                params[target] = value
        url = (
            f"{self.api_url}/projects/{quote(self.organization_slug or '', safe='')}/"
            f"{quote(project_slug, safe='')}/environments/"
        )
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-project-environments-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Sentry environments fetch failed for project %s", project_slug, exc_info=True)
            return [], None
        environments = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return environments, _next_cursor(response)


SentryProjectEnvironmentAdapter = SentryProjectEnvironmentsAdapter


def _environment_signal(
    environment: dict[str, Any],
    *,
    organization_slug: str,
    project_slug: str,
    adapter_name: str,
) -> Signal:
    name = _text(environment.get("name")) or _text(environment.get("displayName")) or _text(environment.get("id"))
    env_id = _text(environment.get("id")) or name
    visibility = _text(environment.get("visibility"))
    url = _text(environment.get("url") or environment.get("permalink")) or (
        f"https://sentry.io/organizations/{organization_slug}/projects/{project_slug}/?environment={quote(name, safe='')}"
    )
    return Signal(
        id=f"sentry-environment:{organization_slug}:{project_slug}:{env_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{project_slug} environment {name}".strip(),
        content=_content(environment, name=name, visibility=visibility),
        url=url,
        author=None,
        published_at=_parse_dt(environment.get("dateCreated") or environment.get("date_created")),
        tags=sorted({"sentry", "environment", organization_slug, project_slug, name, visibility} - {""})[:10],
        credibility=0.66,
        metadata={
            "signal_role": "problem",
            "sentry_organization_slug": organization_slug,
            "sentry_project_slug": project_slug,
            "sentry_environment_id": environment.get("id"),
            "name": name or None,
            "display_name": environment.get("displayName") or environment.get("display_name"),
            "visibility": environment.get("visibility"),
            "date_created": environment.get("dateCreated") or environment.get("date_created"),
            "last_seen": environment.get("lastSeen") or environment.get("last_seen"),
            "raw": environment,
        },
    )


def _content(environment: dict[str, Any], *, name: str, visibility: str) -> str:
    parts = [f"Sentry environment {name or 'unknown'}"]
    if visibility:
        parts.append(f"visibility {visibility}")
    last_seen = _text(environment.get("lastSeen") or environment.get("last_seen"))
    if last_seen:
        parts.append(f"last seen {last_seen}")
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
        if isinstance(item, dict):
            item = item.get("slug") or item.get("id") or item.get("name")
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
