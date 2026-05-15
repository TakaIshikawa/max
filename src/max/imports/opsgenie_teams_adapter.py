"""Opsgenie teams import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_OPSGENIE_API_URL = "https://api.opsgenie.com"


class OpsgenieTeamsImportAdapter(SourceAdapter):
    """Fetch Opsgenie teams and convert them to failure-data signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else (_optional(self._config.get("api_key")) or os.getenv("OPSGENIE_API_KEY"))
        self.api_url = _api_root(api_url or _optional(self._config.get("api_url")) or DEFAULT_OPSGENIE_API_URL)
        self._client = client

    @property
    def name(self) -> str:
        return "opsgenie_teams_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("limit"), default=100, maximum=100)

    @property
    def offset(self) -> int:
        return _non_negative_int(self._config.get("offset"), default=0)

    @property
    def query(self) -> str:
        return _text(self._config.get("query") or self._config.get("q") or self._config.get("search"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.api_key:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            teams = await self._fetch_teams(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for team in teams:
            signal = _team_signal(team, adapter_name=self.name, seen=seen)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_teams(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        teams: list[dict[str, Any]] = []
        offset = self.offset
        while len(teams) < limit:
            page_limit = min(self.page_size, limit - len(teams))
            params: dict[str, Any] = {"limit": page_limit, "offset": offset}
            if self.query:
                params["query"] = self.query

            body = await self._get(client, params=params)
            if body is None:
                return []
            page = _teams_from_body(body)
            if not page:
                break
            teams.extend(page[: limit - len(teams)])
            if len(page) < page_limit or not _has_more(body, page_limit=page_limit):
                break
            offset = _next_offset(body, offset, page_limit)
        return teams[:limit]

    async def _get(self, client: httpx.AsyncClient, *, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            response = await client.get(
                f"{self.api_url}/v2/teams",
                params=params,
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Opsgenie teams fetch failed", exc_info=True)
            return None
        return body if isinstance(body, dict) else {}

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"GenieKey {self.api_key}",
            "User-Agent": "max-opsgenie-teams-import/1",
        }


OpsgenieTeamsAdapter = OpsgenieTeamsImportAdapter


def _team_signal(team: dict[str, Any], *, adapter_name: str, seen: set[str]) -> Signal | None:
    team_id = _optional(team.get("id"))
    if not team_id:
        return None
    signal_id = f"opsgenie-team:{team_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    name = _text(team.get("name")) or f"Opsgenie team {team_id}"
    description = _text(team.get("description"))
    members = _members(team.get("members"))
    member_count = _member_count(team, members)
    tags = _team_tags(team)
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=name,
        content=_content(name=name, description=description, member_count=member_count),
        url=_text(team.get("webUrl") or team.get("web_url") or team.get("url")),
        author=None,
        published_at=_parse_dt(team.get("createdAt") or team.get("created_at")),
        tags=sorted({"opsgenie", "team", *tags} - {""})[:10],
        credibility=0.7,
        metadata={
            "team_id": team.get("id"),
            "name": team.get("name"),
            "description": team.get("description"),
            "member_count": member_count,
            "members": members,
            "tags": tags,
            "created_at": team.get("createdAt") or team.get("created_at"),
            "updated_at": team.get("updatedAt") or team.get("updated_at"),
            "raw": team,
        },
    )


def _content(*, name: str, description: str, member_count: int | None) -> str:
    parts = [f"Opsgenie team {name}"]
    if description:
        parts.append(description)
    if member_count is not None:
        parts.append(f"{member_count} members")
    return "; ".join(parts)


def _teams_from_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("teams", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    teams = body.get("teams")
    return [item for item in teams if isinstance(item, dict)] if isinstance(teams, list) else []


def _has_more(body: dict[str, Any], *, page_limit: int) -> bool:
    for source in (body, body.get("data") if isinstance(body.get("data"), dict) else {}):
        if isinstance(source, dict):
            paging = source.get("paging")
            if isinstance(paging, dict) and paging.get("next"):
                return True
            if isinstance(source.get("more"), bool):
                return bool(source["more"])
    return len(_teams_from_body(body)) >= page_limit


def _next_offset(body: dict[str, Any], offset: int, page_limit: int) -> int:
    for source in (body, body.get("data") if isinstance(body.get("data"), dict) else {}):
        if isinstance(source, dict) and isinstance(source.get("offset"), int):
            return int(source["offset"]) + int(source.get("limit") or page_limit)
    return offset + page_limit


def _members(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    members: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        members.append(
            {
                "id": item.get("id") or user.get("id"),
                "username": item.get("username") or user.get("username"),
                "full_name": item.get("fullName") or item.get("full_name") or user.get("fullName") or user.get("full_name"),
                "role": item.get("role"),
                "raw": item,
            }
        )
    return members


def _member_count(team: dict[str, Any], members: list[dict[str, Any]]) -> int | None:
    for key in ("memberCount", "member_count", "membersCount", "members_count"):
        value = team.get(key)
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            return number
    return len(members) if members else None


def _team_tags(team: dict[str, Any]) -> list[str]:
    value = team.get("tags")
    if isinstance(value, str):
        return [_text(value)] if _text(value) else []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return []


def _api_root(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    for suffix in ("/v2/teams", "/v2"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


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


def _non_negative_int(value: object, *, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, number)


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
