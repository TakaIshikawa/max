"""Azure DevOps build changes import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class AzureDevOpsBuildChangesAdapter(SourceAdapter):
    """Import Azure DevOps build changes as roadmap signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        organization: str | None = None,
        project: str | None = None,
        personal_access_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.organization = organization or _optional(self._config.get("organization")) or os.getenv("AZURE_DEVOPS_ORGANIZATION") or ""
        self.project = project or _optional(self._config.get("project")) or os.getenv("AZURE_DEVOPS_PROJECT") or ""
        configured_token = personal_access_token if personal_access_token is not None else token
        self.personal_access_token = (
            configured_token
            if configured_token is not None
            else (
                _optional(self._config.get("personal_access_token"))
                or _optional(self._config.get("pat"))
                or _optional(self._config.get("token"))
                or os.getenv("AZURE_DEVOPS_PAT")
                or os.getenv("AZURE_DEVOPS_TOKEN")
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or "https://dev.azure.com").rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "azure_devops_build_changes_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def api_version(self) -> str:
        return _text(self._config.get("api_version")) or "7.1"

    @property
    def build_ids(self) -> list[str]:
        return _strings(self._config.get("build_ids") or self._config.get("build_id"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("top") or self._config.get("$top"), default=100, maximum=1000)

    @property
    def per_build_limit(self) -> int | None:
        value = self._config.get("per_build_limit")
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @property
    def base_url(self) -> str:
        return f"{self.api_url}/{self.organization}/{self.project}".rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.organization and self.project and self.personal_access_token and self.build_ids):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for build_id in self.build_ids:
                if len(signals) >= limit:
                    break
                build_limit = limit - len(signals)
                if self.per_build_limit:
                    build_limit = min(build_limit, self.per_build_limit)
                changes = await self._fetch_changes(client, build_id=build_id, limit=build_limit)
                for change in changes:
                    signals.append(
                        _change_signal(
                            change,
                            adapter_name=self.name,
                            organization=self.organization,
                            project=self.project,
                            build_id=build_id,
                        )
                    )
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_changes(
        self,
        client: httpx.AsyncClient,
        *,
        build_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        seen: set[str] = set()
        continuation_token: str | None = None
        while len(changes) < limit:
            page_size = min(self.page_size, limit - len(changes))
            page_changes, next_token = await self._fetch_page(
                client,
                build_id=build_id,
                top=page_size,
                continuation_token=continuation_token,
            )
            if not page_changes:
                break
            for change in page_changes:
                change_id = _change_id(change)
                if not change_id or change_id in seen:
                    continue
                seen.add(change_id)
                changes.append(change)
                if len(changes) >= limit:
                    break
            if next_token and len(changes) < limit:
                continuation_token = next_token
            else:
                break
        return changes[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        build_id: str,
        top: int,
        continuation_token: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"api-version": self.api_version, "$top": top}
        if continuation_token:
            params["continuationToken"] = continuation_token
        try:
            response = await client.get(
                f"{self.base_url}/_apis/build/builds/{build_id}/changes",
                auth=("", self.personal_access_token or ""),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "max-azure-devops-build-changes-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Azure DevOps build changes fetch failed for build %s", build_id, exc_info=True)
            return [], None
        values = body.get("value") if isinstance(body, dict) else None
        changes = [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []
        return changes, _optional(response.headers.get("x-ms-continuationtoken"))


AzureDevOpsBuildChangesImportAdapter = AzureDevOpsBuildChangesAdapter


def _change_signal(
    change: dict[str, Any],
    *,
    adapter_name: str,
    organization: str,
    project: str,
    build_id: str,
) -> Signal:
    change_id = _change_id(change)
    message = _text(change.get("message"))
    author = change.get("author") if isinstance(change.get("author"), dict) else {}
    author_name = _optional(author.get("displayName") or author.get("name") or author.get("uniqueName"))
    location = _text(change.get("location"))
    url = location or f"https://dev.azure.com/{organization}/{project}/_build/results?buildId={build_id}"
    return Signal(
        id=f"azure-devops-build-change:{organization}/{project}:{build_id}:{change_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{project} build {build_id} change {change_id}",
        content=message or f"Azure DevOps build {build_id} change {change_id}",
        url=url,
        author=author_name,
        published_at=_parse_dt(change.get("timestamp")),
        tags=sorted({"azure-devops", "build-change", _text(change.get("type"))} - {""})[:10],
        credibility=0.7,
        metadata={
            "organization": organization,
            "project": project,
            "build_id": build_id,
            "change_id": change_id,
            "id": change.get("id"),
            "type": change.get("type"),
            "message": change.get("message"),
            "author": _author_summary(author),
            "timestamp": change.get("timestamp"),
            "location": change.get("location"),
            "raw": change,
        },
    )


def _change_id(change: dict[str, Any]) -> str:
    return _text(change.get("id") or change.get("commitId") or change.get("changeId") or change.get("version"))


def _author_summary(author: dict[str, Any]) -> dict[str, Any]:
    return {
        key: author.get(key)
        for key in ("displayName", "name", "uniqueName", "id", "email")
        if author.get(key) is not None
    }


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


def _strings(value: object) -> list[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
