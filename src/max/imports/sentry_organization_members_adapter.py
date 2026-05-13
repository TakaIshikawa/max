"""Sentry organization members import adapter."""

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


class SentryOrganizationMembersAdapter(SourceAdapter):
    """Import Sentry organization members as team/market signals."""

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
        return "sentry_organization_members_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def organization_slug(self) -> str | None:
        return _optional(self._config.get("organization_slug") or self._config.get("org"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=25, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.organization_slug:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            members = await self._fetch_members(client, limit=limit)
            return [
                _member_signal(member, organization_slug=self.organization_slug, adapter_name=self.name)
                for member in members
                if isinstance(member, dict)
            ][:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_members(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(members) < limit:
            page_size = min(self.page_size, limit - len(members))
            page_members, cursor = await self._fetch_page(client, cursor=cursor, page_size=page_size)
            if not page_members:
                break
            members.extend(page_members[: limit - len(members)])
            if not cursor:
                break
        return members[:limit]

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
        for key in ("query", "team", "project"):
            value = _optional(self._config.get(key))
            if value:
                params[key] = value
        url = f"{self.api_url}/organizations/{self.organization_slug}/members/"
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-organization-members-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Sentry organization members fetch failed for %s", self.organization_slug, exc_info=True)
            return [], None
        members = [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []
        return members, _next_cursor(response)


SentryOrganizationMemberAdapter = SentryOrganizationMembersAdapter


def _member_signal(member: dict[str, Any], *, organization_slug: str, adapter_name: str) -> Signal:
    member_id = _text(member.get("id"))
    user = member.get("user") if isinstance(member.get("user"), dict) else {}
    email = _text(member.get("email") or user.get("email"))
    name = _text(member.get("name") or user.get("name") or user.get("username") or email)
    role = _text(member.get("roleName") or member.get("role"))
    invite_status = _invite_status(member)
    teams = _teams(member.get("teams"))
    flags = _flags(member)
    return Signal(
        id=f"sentry-organization-member:{organization_slug}:{member_id or email}",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"Sentry member {name or member_id}".strip(),
        content=_content(name=name, role=role, teams=teams, invite_status=invite_status),
        url=_text(member.get("url")),
        author=None,
        published_at=_parse_dt(member.get("dateCreated") or member.get("date_added")),
        tags=sorted({"sentry", "organization-member", role, invite_status} - {""})[:10],
        credibility=0.62,
        metadata={
            "signal_role": "market",
            "sentry_organization_slug": organization_slug,
            "sentry_member_id": member.get("id"),
            "member_id": member.get("id"),
            "email": email or None,
            "name": name or None,
            "role": member.get("role"),
            "role_name": member.get("roleName"),
            "teams": teams,
            "flags": flags,
            "invite_status": invite_status or None,
            "pending": member.get("pending"),
            "expired": member.get("expired"),
            "date_created": member.get("dateCreated") or member.get("date_added"),
            "user": _user_summary(user),
            "raw": member,
        },
    )


def _content(*, name: str, role: str, teams: list[dict[str, Any]], invite_status: str) -> str:
    parts = [f"Sentry organization member {name or 'unknown'}"]
    if role:
        parts.append(f"role {role}")
    if invite_status:
        parts.append(f"invite {invite_status}")
    if teams:
        team_names = ", ".join(_text(team.get("slug") or team.get("name")) for team in teams[:5])
        if team_names:
            parts.append(f"teams {team_names}")
    return "; ".join(part for part in parts if part)


def _invite_status(member: dict[str, Any]) -> str:
    invite_status = _text(member.get("inviteStatus") or member.get("invite_status"))
    if invite_status:
        return invite_status
    if member.get("expired") is True:
        return "expired"
    if member.get("pending") is True:
        return "pending"
    if member.get("pending") is False:
        return "accepted"
    return ""


def _teams(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    teams: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        teams.append(
            {
                key: item.get(key)
                for key in ("id", "slug", "name")
                if item.get(key) is not None
            }
        )
    return teams


def _flags(member: dict[str, Any]) -> dict[str, Any]:
    flags = member.get("flags") if isinstance(member.get("flags"), dict) else {}
    result = dict(flags)
    for key in ("pending", "expired", "has2fa", "isOwner"):
        if member.get(key) is not None:
            result[key] = member.get(key)
    return result


def _user_summary(user: dict[str, Any]) -> dict[str, Any]:
    return {
        key: user.get(key)
        for key in ("id", "name", "username", "email")
        if user.get(key) is not None
    }


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


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
