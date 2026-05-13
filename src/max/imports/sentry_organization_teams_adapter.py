"""Sentry organization teams import adapter."""

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


class SentryOrganizationTeamsAdapter(SourceAdapter):
    """Import Sentry organization teams as failure-data signals."""

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
                    or os.getenv("SENTRY_TOKEN")
                )
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or SENTRY_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "sentry_organization_teams_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def organization_slug(self) -> str | None:
        return _optional(
            self._config.get("organization_slug")
            or self._config.get("org_slug")
            or self._config.get("organization")
            or self._config.get("org")
        )

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=25, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.organization_slug:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            teams = await self._fetch_teams(client, limit=limit)
            return [
                _team_signal(team, organization_slug=self.organization_slug, adapter_name=self.name)
                for team in teams
                if isinstance(team, dict)
            ][:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_teams(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        teams: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(teams) < limit:
            page_size = min(self.page_size, limit - len(teams))
            page_teams, cursor = await self._fetch_page(client, cursor=cursor, page_size=page_size)
            if not page_teams:
                break
            teams.extend(page_teams[: limit - len(teams)])
            if not cursor:
                break
        return teams[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        cursor: str | None,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"per_page": page_size}
        if cursor:
            params["cursor"] = cursor
        query = _optional(self._config.get("query"))
        if query:
            params["query"] = query
        url = f"{self.api_url}/organizations/{self.organization_slug}/teams/"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-organization-teams-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Sentry organization teams fetch failed for %s", self.organization_slug, exc_info=True)
            return [], None
        teams = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return teams, _next_cursor(response)


SentryOrganizationTeamAdapter = SentryOrganizationTeamsAdapter


def _team_signal(team: dict[str, Any], *, organization_slug: str, adapter_name: str) -> Signal:
    team_id = _text(team.get("id"))
    slug = _text(team.get("slug"))
    name = _text(team.get("name")) or slug or team_id
    member_count = _int(team.get("memberCount") or team.get("member_count"))
    project_count = _int(team.get("projectCount") or team.get("project_count"))
    date_created = team.get("dateCreated") or team.get("date_created")
    return Signal(
        id=f"sentry-organization-team:{organization_slug}:{slug or team_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"Sentry team {name}".strip(),
        content=_content(name=name, slug=slug, member_count=member_count, project_count=project_count),
        url=_team_url(team, organization_slug=organization_slug, slug=slug),
        published_at=_parse_dt(date_created),
        tags=sorted({"sentry", "team", slug} - {""})[:10],
        credibility=0.62,
        metadata={
            "signal_role": "failure_data",
            "sentry_organization_slug": organization_slug,
            "sentry_team_id": team.get("id"),
            "team_id": team.get("id"),
            "slug": slug or None,
            "name": name or None,
            "member_count": member_count,
            "project_count": project_count,
            "date_created": date_created,
            "is_member": team.get("isMember") if team.get("isMember") is not None else team.get("is_member"),
            "team_role": team.get("teamRole") or team.get("team_role"),
            "raw": team,
        },
    )


def _content(*, name: str, slug: str, member_count: int | None, project_count: int | None) -> str:
    parts = [f"Sentry organization team {name or slug or 'unknown'}"]
    if slug and slug != name:
        parts.append(f"slug {slug}")
    if member_count is not None:
        parts.append(f"{member_count} members")
    if project_count is not None:
        parts.append(f"{project_count} projects")
    return "; ".join(parts)


def _team_url(team: dict[str, Any], *, organization_slug: str, slug: str) -> str:
    url = _text(team.get("url") or team.get("web_url"))
    if url:
        return url
    if organization_slug and slug:
        return f"https://sentry.io/organizations/{organization_slug}/teams/{slug}/"
    return ""


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


def _int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
