"""GitLab package registry import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITLAB_API = "https://gitlab.com/api/v4"


class GitLabPackageRegistryImportAdapter(SourceAdapter):
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
            else (
                _optional(self._config.get("token"))
                or os.getenv("GITLAB_PRIVATE_TOKEN")
                or os.getenv("GITLAB_TOKEN")
            )
        )
        self.api_url = _api_url(
            api_url
            or _optional(self._config.get("api_url"))
            or _optional(self._config.get("gitlab_url"))
            or _optional(self._config.get("base_url"))
            or os.getenv("GITLAB_API_URL")
            or GITLAB_API
        )
        self._client = client

    @property
    def name(self) -> str:
        return "gitlab_package_registry_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def projects(self) -> list[str]:
        return _strings(
            self._config.get("projects")
            or self._config.get("project_ids")
            or self._config.get("project_paths")
            or self._config.get("project_id")
            or self._config.get("project_path")
        )

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=20, maximum=100)

    @property
    def per_project_limit(self) -> int | None:
        value = self._config.get("per_project_limit")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.projects:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for project in self.projects:
                if len(signals) >= limit:
                    break
                project_limit = min(self.per_project_limit or limit, limit - len(signals))
                packages = await self._fetch_project(client, project=project, limit=project_limit)
                signals.extend(
                    _package_signal(item, project, self.name)
                    for item in packages
                    if isinstance(item, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_project(
        self,
        client: httpx.AsyncClient,
        *,
        project: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        packages: list[dict[str, Any]] = []
        page = 1
        while len(packages) < limit:
            page_size = min(self.per_page, limit - len(packages))
            body = await self._get(
                client,
                f"{self.api_url}/projects/{_encode_project(project)}/packages",
                params=_params(self._config, page=page, per_page=page_size),
            )
            if not isinstance(body, list) or not body:
                break
            packages.extend(item for item in body if isinstance(item, dict))
            if len(body) < page_size:
                break
            page += 1
        return packages[:limit]

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
                headers={
                    "PRIVATE-TOKEN": self.token or "",
                    "Accept": "application/json",
                    "User-Agent": "max-gitlab-package-registry-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitLab package registry fetch failed for %s", url, exc_info=True)
            return []


GitLabPackageRegistryAdapter = GitLabPackageRegistryImportAdapter


def _package_signal(package: dict[str, Any], project: str, adapter_name: str) -> Signal:
    package_id = _text(package.get("id"))
    name = _text(package.get("name"))
    version = _text(package.get("version"))
    package_type = _text(package.get("package_type"))
    status = _text(package.get("status"))
    title_bits = [project, name]
    if version:
        title_bits.append(version)
    pipeline = package.get("pipeline") if isinstance(package.get("pipeline"), dict) else {}
    return Signal(
        id=f"gitlab-package:{project}:{package_id or name}:{version or package_type}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=" ".join(bit for bit in title_bits if bit) or f"{project} package",
        content=_package_content(package),
        url=_package_url(package),
        author=_optional(package.get("creator_id")),
        published_at=_parse_dt(package.get("created_at")),
        tags=sorted({"gitlab", "package", package_type, status} - {""})[:10],
        credibility=0.7,
        metadata={
            "signal_role": "readiness",
            "project_id": package.get("project_id"),
            "project_path": project,
            "package_id": package.get("id"),
            "name": name or None,
            "version": version or None,
            "package_type": package_type or None,
            "status": status or None,
            "pipeline": _pipeline_summary(pipeline),
            "created_at": package.get("created_at"),
            "updated_at": package.get("updated_at"),
            "url": _package_url(package) or None,
            "raw": package,
        },
    )


def _api_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.endswith("/api/v4"):
        url = f"{url}/api/v4"
    return url


def _params(config: dict, *, page: int, per_page: int) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    for key in ("package_type", "status", "order_by", "sort"):
        value = _optional(config.get(key))
        if value:
            params[key] = value
    return params


def _encode_project(project: str) -> str:
    return quote(unquote(str(project).strip()), safe="")


def _package_content(package: dict[str, Any]) -> str:
    parts = [
        f"name: {_text(package.get('name'))}",
        f"version: {_text(package.get('version'))}",
        f"type: {_text(package.get('package_type'))}",
        f"status: {_text(package.get('status'))}",
    ]
    pipeline = package.get("pipeline")
    if isinstance(pipeline, dict) and pipeline:
        pipeline_summary = " ".join(
            bit
            for bit in (
                f"pipeline:{_text(pipeline.get('id'))}",
                _text(pipeline.get("status")),
                _text(pipeline.get("ref")),
                _text(pipeline.get("sha")),
            )
            if bit
        )
        if pipeline_summary:
            parts.append(pipeline_summary)
    return "\n".join(part for part in parts if not part.endswith(": "))


def _package_url(package: dict[str, Any]) -> str:
    return _text(package.get("_links", {}).get("web_path") if isinstance(package.get("_links"), dict) else "") or _text(
        package.get("web_url") or package.get("url")
    )


def _pipeline_summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": value.get("id"),
        "iid": value.get("iid"),
        "status": _text(value.get("status")) or None,
        "ref": _text(value.get("ref")) or None,
        "sha": _text(value.get("sha")) or None,
        "web_url": value.get("web_url"),
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
