"""GitLab issue notes import adapter."""

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


class GitLabIssueNotesAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        private_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        gitlab_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            private_token
            if private_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("private_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("GITLAB_TOKEN")
                )
            )
        )
        configured_url = api_url or _optional(self._config.get("api_url"))
        base_url = gitlab_url or _optional(self._config.get("gitlab_url"))
        self.api_url = (configured_url or _api_url_from_gitlab_url(base_url) or GITLAB_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_issue_notes_import"

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
    def issue_iids(self) -> list[str]:
        return _strings(
            self._config.get("issue_iids")
            or self._config.get("issues")
            or self._config.get("issue_iid")
        )

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    @property
    def per_issue_limit(self) -> int | None:
        value = self._config.get("per_issue_limit")
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @property
    def include_system_notes(self) -> bool:
        return bool(self._config.get("system_notes"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.project_ids or not self.issue_iids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project_id in self.project_ids:
                for issue_iid in self.issue_iids:
                    if len(signals) >= limit:
                        break
                    issue_limit = limit - len(signals)
                    if self.per_issue_limit:
                        issue_limit = min(issue_limit, self.per_issue_limit)
                    notes = await self._fetch_issue_notes(
                        client,
                        project_id=project_id,
                        issue_iid=issue_iid,
                        limit=issue_limit,
                    )
                    signals.extend(
                        _note_signal(note, project_id, issue_iid, self.name)
                        for note in notes
                        if isinstance(note, dict)
                    )
                if len(signals) >= limit:
                    break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_issue_notes(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        issue_iid: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        page = 1
        while len(notes) < limit:
            page_size = min(self.page_size, max(limit - len(notes), 1))
            page_notes = await self._fetch_page(
                client,
                project_id=project_id,
                issue_iid=issue_iid,
                page=page,
                page_size=page_size,
            )
            if not page_notes:
                break
            filtered = [
                note
                for note in page_notes
                if self.include_system_notes or not bool(note.get("system"))
            ]
            notes.extend(filtered[: limit - len(notes)])
            if len(page_notes) < page_size:
                break
            page += 1
        return notes[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        project_id: str,
        issue_iid: str,
        page: int,
        page_size: int,
    ) -> list[dict[str, Any]]:
        project = quote(project_id, safe="")
        issue = quote(issue_iid, safe="")
        url = f"{self.api_url}/projects/{project}/issues/{issue}/notes"
        try:
            response = await client.get(
                url,
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-issue-notes-import/1",
                },
                params={"page": page, "per_page": page_size},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitLab issue notes fetch failed for %s issue %s", project_id, issue_iid, exc_info=True)
            return []
        return [item for item in body if isinstance(item, dict)] if isinstance(body, list) else []


GitLabIssueNoteAdapter = GitLabIssueNotesAdapter


def _note_signal(note: dict[str, Any], project_id: str, issue_iid: str, adapter_name: str) -> Signal:
    author = note.get("author") if isinstance(note.get("author"), dict) else {}
    note_id = _text(note.get("id"))
    body = _text(note.get("body"))
    username = _optional(author.get("username") or author.get("name"))
    return Signal(
        id=f"gitlab-issue-note:{project_id}:{issue_iid}:{note_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"GitLab issue {issue_iid} note",
        content=body[:1000],
        url=_text(note.get("url") or note.get("web_url")),
        author=username,
        published_at=_parse_dt(note.get("created_at")),
        tags=sorted({"gitlab", "issue-note", "system-note" if note.get("system") else ""} - {""})[:10],
        credibility=0.65,
        metadata={
            "gitlab_note_id": note.get("id"),
            "project_id": project_id,
            "issue_iid": issue_iid,
            "body": body,
            "system": bool(note.get("system")),
            "author": {
                "id": author.get("id"),
                "username": author.get("username"),
                "name": author.get("name"),
                "web_url": author.get("web_url"),
            },
            "created_at": note.get("created_at"),
            "updated_at": note.get("updated_at"),
            "noteable_id": note.get("noteable_id"),
            "noteable_iid": note.get("noteable_iid"),
            "url": note.get("url") or note.get("web_url"),
            "raw": note,
        },
    )


def _api_url_from_gitlab_url(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.rstrip("/")
    if stripped.endswith("/api/v4"):
        return stripped
    return f"{stripped}/api/v4"


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
    return [str(item).strip() for item in value if str(item).strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
