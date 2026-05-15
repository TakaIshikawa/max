"""Azure DevOps classic releases import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class AzureDevOpsReleasesAdapter(SourceAdapter):
    """Import Azure DevOps classic releases as Max signals."""

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
        self.api_url = (api_url or _optional(self._config.get("api_url")) or "https://vsrm.dev.azure.com").rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "azure_devops_releases_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def api_version(self) -> str:
        return _text(self._config.get("api_version")) or "7.1"

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page") or self._config.get("$top"), default=100, maximum=1000)

    @property
    def continuation_token(self) -> str | None:
        return _optional(self._config.get("continuation_token") or self._config.get("continuationToken"))

    @property
    def base_url(self) -> str:
        return f"{self.api_url}/{self.organization}/{self.project}".rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.organization and self.project and self.personal_access_token):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            releases = await self._fetch_releases(client, limit=limit)
            return [
                _release_signal(
                    release,
                    adapter_name=self.name,
                    organization=self.organization,
                    project=self.project,
                )
                for release in releases[:limit]
            ]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_releases(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        releases: list[dict[str, Any]] = []
        continuation_token = self.continuation_token
        while len(releases) < limit:
            page_size = min(self.page_size, limit - len(releases))
            page, continuation_token = await self._fetch_page(
                client,
                page_size=page_size,
                continuation_token=continuation_token,
            )
            if page is None:
                return []
            if not page:
                break
            releases.extend(page[: limit - len(releases)])
            if not continuation_token or len(page) < page_size:
                break
        return releases[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        page_size: int,
        continuation_token: str | None,
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        params = self._params(page_size=page_size, continuation_token=continuation_token)
        try:
            response = await client.get(
                f"{self.base_url}/_apis/release/releases",
                auth=("", self.personal_access_token or ""),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "max-azure-devops-releases-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Azure DevOps releases fetch failed for %s/%s", self.organization, self.project, exc_info=True)
            return None, None

        values = body.get("value") if isinstance(body, dict) else body
        if not isinstance(values, list):
            return None, None
        next_token = (
            response.headers.get("x-ms-continuationtoken")
            or response.headers.get("X-MS-ContinuationToken")
            or response.headers.get("continuationToken")
        )
        return [item for item in values if isinstance(item, dict)], _optional(next_token)

    def _params(self, *, page_size: int, continuation_token: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"api-version": self.api_version, "$top": page_size}
        if continuation_token:
            params["continuationToken"] = continuation_token
        for config_key, param_key in (
            ("definition_id", "definitionId"),
            ("definitionId", "definitionId"),
            ("status_filter", "statusFilter"),
            ("statusFilter", "statusFilter"),
            ("min_created_time", "minCreatedTime"),
            ("minCreatedTime", "minCreatedTime"),
            ("max_created_time", "maxCreatedTime"),
            ("maxCreatedTime", "maxCreatedTime"),
        ):
            value = _optional(self._config.get(config_key))
            if value and param_key not in params:
                params[param_key] = value
        return params


AzureDevOpsReleasesImportAdapter = AzureDevOpsReleasesAdapter
AzureDevOpsReleaseAdapter = AzureDevOpsReleasesAdapter


def _release_signal(
    release: dict[str, Any],
    *,
    adapter_name: str,
    organization: str,
    project: str,
) -> Signal:
    release_id = _text(release.get("id"))
    name = _text(release.get("name")) or f"release {release_id}"
    status = _text(release.get("status"))
    reason = _text(release.get("reason"))
    created_by = _identity(release.get("createdBy") or release.get("created_by"))
    created_on = release.get("createdOn") or release.get("created_on")
    definition = _definition(release.get("releaseDefinition") or release.get("definition"))
    environments = [_environment(item) for item in release.get("environments", []) if isinstance(item, dict)]
    web_url = _web_url(release, organization, project, release_id)
    signal_role = "problem" if _failure_status(status, environments) else "solution"
    return Signal(
        id=f"azure-devops-release:{release_id}",
        source_type=SignalSourceType.FAILURE_DATA if signal_role == "problem" else SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{project} release {name} {status or 'unknown'}",
        content=_content(name=name, status=status, reason=reason, definition=definition, environments=environments),
        url=web_url,
        author=created_by.get("display_name") or created_by.get("unique_name"),
        published_at=_parse_dt(created_on),
        tags=sorted({"azure-devops", "release", status.lower(), reason.lower(), definition.get("name", "")} - {""})[:10],
        credibility=0.7,
        metadata={
            "signal_role": signal_role,
            "organization": organization,
            "project": project,
            "release_id": release.get("id"),
            "name": release.get("name"),
            "status": release.get("status"),
            "reason": release.get("reason"),
            "created_by": created_by,
            "created_on": created_on,
            "definition": definition,
            "environments": environments,
            "web_url": web_url,
            "url": release.get("url"),
            "raw": release,
        },
    )


def _content(
    *,
    name: str,
    status: str,
    reason: str,
    definition: dict[str, Any],
    environments: list[dict[str, Any]],
) -> str:
    parts = [f"Azure DevOps release {name}"]
    if status:
        parts.append(f"status {status}")
    if reason:
        parts.append(f"reason {reason}")
    if definition.get("name"):
        parts.append(f"definition {definition['name']}")
    failed = [env["name"] for env in environments if _text(env.get("status")).lower() in {"failed", "rejected", "canceled", "cancelled"} and env.get("name")]
    if failed:
        parts.append("failed environments " + ", ".join(failed))
    return "; ".join(parts)


def _web_url(release: dict[str, Any], organization: str, project: str, release_id: str) -> str:
    links = release.get("_links") if isinstance(release.get("_links"), dict) else {}
    web = links.get("web") if isinstance(links.get("web"), dict) else {}
    href = _text(web.get("href"))
    if href:
        return href
    url = _text(release.get("webAccessUri") or release.get("webUrl") or release.get("web_url"))
    if url:
        return url
    return f"https://dev.azure.com/{organization}/{project}/_releaseProgress?releaseId={release_id}" if release_id else ""


def _identity(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        text = _text(value)
        return {"display_name": text, "unique_name": None, "id": None} if text else {}
    return {
        "display_name": value.get("displayName") or value.get("display_name"),
        "unique_name": value.get("uniqueName") or value.get("unique_name") or value.get("email"),
        "id": value.get("id"),
        "url": value.get("url"),
        "image_url": value.get("imageUrl") or value.get("image_url"),
    }


def _definition(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "id": value.get("id"),
        "name": value.get("name"),
        "path": value.get("path"),
        "url": value.get("url"),
    }


def _environment(value: dict[str, Any]) -> dict[str, Any]:
    deploy_steps = value.get("deploySteps") if isinstance(value.get("deploySteps"), list) else []
    return {
        "id": value.get("id"),
        "name": value.get("name"),
        "status": value.get("status"),
        "rank": value.get("rank"),
        "created_on": value.get("createdOn") or value.get("created_on"),
        "modified_on": value.get("modifiedOn") or value.get("modified_on"),
        "deploy_steps": [_deploy_step(step) for step in deploy_steps if isinstance(step, dict)],
    }


def _deploy_step(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": value.get("id"),
        "status": value.get("status"),
        "reason": value.get("reason"),
        "attempt": value.get("attempt"),
        "last_modified_on": value.get("lastModifiedOn") or value.get("last_modified_on"),
    }


def _failure_status(status: str, environments: list[dict[str, Any]]) -> bool:
    failure_values = {"abandoned", "canceled", "cancelled", "failed", "rejected"}
    if status.lower() in failure_values:
        return True
    return any(_text(environment.get("status")).lower() in failure_values for environment in environments)


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
