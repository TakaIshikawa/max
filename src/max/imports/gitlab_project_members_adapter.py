"""GitLab project members import adapter."""

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


class GitLabProjectMembersAdapter(SourceAdapter):
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
            else (_optional(self._config.get("token")) or os.getenv("GITLAB_TOKEN"))
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or GITLAB_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_project_members_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def project_ids(self) -> list[str]:
        return _strings(
            self._config.get("project_ids")
            or self._config.get("projects")
            or self._config.get("project_id")
        )

    @property
    def states(self) -> list[str]:
        return [
            state.lower()
            for state in _strings(self._config.get("states") or self._config.get("state"))
        ]

    @property
    def include_inherited(self) -> bool:
        return bool(self._config.get("include_inherited"))

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project_id in self.project_ids:
                if len(signals) >= limit:
                    break
                members = await self._fetch_project_members(
                    client,
                    project_id=project_id,
                    limit=limit - len(signals),
                )
                signals.extend(
                    _member_signal(member, project_id, self.name)
                    for member in members
                    if isinstance(member, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project_members(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        page = 1
        while len(members) < limit:
            page_size = min(self.per_page, limit - len(members))
            body = await self._get(
                client,
                f"{self.api_url}/projects/{quote(project_id, safe='')}/{self._members_path}",
                params={"per_page": page_size, "page": page},
            )
            if not isinstance(body, list) or not body:
                break
            filtered = [_member for _member in body if _matches_state(_member, self.states)]
            members.extend(filtered)
            if len(body) < page_size:
                break
            page += 1
        return members[:limit]

    @property
    def _members_path(self) -> str:
        return "members/all" if self.include_inherited else "members"

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
                headers={"PRIVATE-TOKEN": self.token or "", "Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitLab project member fetch failed for %s", url, exc_info=True)
            return []


GitLabProjectMemberAdapter = GitLabProjectMembersAdapter


def _member_signal(member: dict[str, Any], project_id: str, adapter_name: str) -> Signal:
    username = _text(member.get("username"))
    name = _text(member.get("name"))
    state = _text(member.get("state"))
    access_level = _int(member.get("access_level"))
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=name or username or f"GitLab project {project_id} member",
        content=f"{name or username} is a GitLab project member with access level {access_level}.".strip(),
        url=_text(member.get("web_url")),
        author=username or None,
        published_at=_parse_dt(member.get("created_at")),
        tags=sorted({"gitlab", "project-member", state, _access_level_tag(access_level)} - {""})[
            :10
        ],
        credibility=0.65,
        metadata={
            "gitlab_member_id": member.get("id"),
            "project_id": project_id,
            "name": name,
            "username": username,
            "access_level": access_level,
            "state": member.get("state"),
            "created_at": member.get("created_at"),
            "web_url": member.get("web_url"),
            "avatar_url": member.get("avatar_url"),
            "expires_at": member.get("expires_at"),
            "evidence": ["adoption", "stakeholder", "implementation-risk"],
        },
    )


def _matches_state(member: object, states: list[str]) -> bool:
    if not states or not isinstance(member, dict):
        return True
    return _text(member.get("state")).lower() in states


def _access_level_tag(access_level: int) -> str:
    if access_level >= 40:
        return "maintainer"
    if access_level >= 30:
        return "developer"
    if access_level >= 20:
        return "reporter"
    if access_level >= 10:
        return "guest"
    return ""


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
    text = str(value).strip() if value is not None else ""
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
