"""Bitbucket deployments import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
BITBUCKET_API = "https://api.bitbucket.org/2.0"


class BitbucketDeploymentsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        username: str | None = None,
        app_password: str | None = None,
        bearer_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.username = username if username is not None else (
            _optional(self._config.get("username")) or os.getenv("BITBUCKET_USERNAME")
        )
        self.app_password = app_password if app_password is not None else (
            _optional(self._config.get("app_password")) or os.getenv("BITBUCKET_APP_PASSWORD")
        )
        self.bearer_token = bearer_token if bearer_token is not None else (
            token
            or _optional(self._config.get("bearer_token"))
            or _optional(self._config.get("token"))
            or os.getenv("BITBUCKET_BEARER_TOKEN")
            or os.getenv("BITBUCKET_TOKEN")
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or BITBUCKET_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "bitbucket_deployments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def workspace(self) -> str | None:
        return _optional(self._config.get("workspace"))

    @property
    def repo_slug(self) -> str | None:
        repository = _optional(self._config.get("repo_slug") or self._config.get("repository"))
        if repository and "/" in repository:
            return repository.rsplit("/", 1)[1]
        return repository

    @property
    def environments(self) -> list[str]:
        return _strings(self._config.get("environments") or self._config.get("environment"))

    @property
    def statuses(self) -> list[str]:
        return _strings(self._config.get("statuses") or self._config.get("status"))

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("page_len") or self._config.get("pagelen"),
            default=30,
            maximum=100,
        )

    @property
    def _has_auth(self) -> bool:
        return bool(self.bearer_token or (self.username and self.app_password))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.workspace and self.repo_slug and self._has_auth):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            deployments = await self._fetch_deployments(client, limit=limit)
            return [
                _deployment_signal(deployment, self.workspace, self.repo_slug, self.name)
                for deployment in deployments[:limit]
            ]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_deployments(
        self,
        client: httpx.AsyncClient,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        deployments: list[dict[str, Any]] = []
        url: str | None = f"{self.api_url}/repositories/{self.workspace}/{self.repo_slug}/deployments/"
        params: dict[str, Any] | None = {"pagelen": min(self.page_size, limit)}
        if self.environments:
            params["environment"] = self.environments
        if self.statuses:
            params["status"] = self.statuses

        while url and len(deployments) < limit:
            body = await self._get(client, url, params=params)
            values = body.get("values") if isinstance(body.get("values"), list) else []
            if not values:
                break
            deployments.extend(item for item in values if isinstance(item, dict))
            url = _optional(body.get("next"))
            params = None
        return deployments[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": "max-bitbucket-deployments-import/1"}
        auth = None
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        else:
            auth = httpx.BasicAuth(self.username or "", self.app_password or "")
        try:
            response = await client.get(url, headers=headers, auth=auth, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Bitbucket deployments fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


BitbucketDeploymentsImportAdapter = BitbucketDeploymentsAdapter


def _deployment_signal(
    deployment: dict[str, Any],
    workspace: str,
    repo_slug: str,
    adapter_name: str,
) -> Signal:
    deployment_uuid = _text(deployment.get("uuid") or deployment.get("id")) or _text(deployment.get("created_on"))
    state = _nested(deployment.get("state"))
    environment = _nested(deployment.get("environment"))
    step = _nested(deployment.get("step"))
    commit = _nested(deployment.get("commit"))
    deployer = _nested(deployment.get("deployer") or deployment.get("creator") or deployment.get("user"))
    release = _nested(deployment.get("release"))
    status = _optional(state.get("name") or state.get("status") or state.get("type") or deployment.get("status"))
    environment_name = _optional(environment.get("name") or environment.get("slug") or deployment.get("environment"))
    release_version = _optional(release.get("version") or release.get("name") or deployment.get("release_version"))
    url = _deployment_url(deployment)
    content = _deployment_content(status=status, environment=environment_name, release_version=release_version, commit=commit)

    return Signal(
        id=f"bitbucket-deployment:{workspace}:{repo_slug}:{deployment_uuid or 'unknown'}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"{workspace}/{repo_slug} deployment {status or 'unknown'}",
        content=content[:1000],
        url=url,
        author=_optional(deployer.get("display_name") or deployer.get("nickname") or deployer.get("username")),
        published_at=_parse_dt(deployment.get("created_on") or deployment.get("started_on")),
        tags=sorted({"bitbucket", "deployment", (status or "").lower(), (environment_name or "").lower()} - {""})[:10],
        credibility=0.65,
        metadata={
            "deployment_uuid": deployment.get("uuid") or deployment.get("id"),
            "workspace": workspace,
            "repository": repo_slug,
            "state": state,
            "status": status,
            "environment": environment,
            "environment_name": environment_name,
            "step": step,
            "commit": commit,
            "deployer": _summary(deployer),
            "release": release,
            "release_version": release_version,
            "started_on": deployment.get("started_on") or deployment.get("created_on"),
            "completed_on": deployment.get("completed_on") or deployment.get("updated_on"),
            "created_on": deployment.get("created_on"),
            "updated_on": deployment.get("updated_on"),
            "url": url,
            "links": deployment.get("links"),
            "raw": deployment,
        },
    )


def _deployment_content(
    *,
    status: str | None,
    environment: str | None,
    release_version: str | None,
    commit: dict[str, Any],
) -> str:
    parts = [
        f"status {status}" if status else "",
        f"environment {environment}" if environment else "",
        f"release {release_version}" if release_version else "",
        f"commit {_optional(commit.get('hash'))}" if commit.get("hash") else "",
    ]
    return ", ".join(part for part in parts if part) or "Bitbucket deployment"


def _deployment_url(deployment: dict[str, Any]) -> str:
    links = deployment.get("links") if isinstance(deployment.get("links"), dict) else {}
    for key in ("html", "self"):
        href = _link_href(links.get(key))
        if href:
            return href
    return ""


def _link_href(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("href"))
    return ""


def _nested(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "id": value.get("id"),
        "uuid": value.get("uuid"),
        "display_name": value.get("display_name"),
        "nickname": value.get("nickname"),
        "username": value.get("username"),
        "links": value.get("links"),
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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
