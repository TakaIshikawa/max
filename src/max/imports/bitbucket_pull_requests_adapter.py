"""Bitbucket pull request import adapter."""

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


class BitbucketPullRequestsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        username: str | None = None,
        app_password: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.username = username if username is not None else os.getenv("BITBUCKET_USERNAME")
        self.app_password = (
            app_password if app_password is not None else os.getenv("BITBUCKET_APP_PASSWORD")
        )
        self.token = token if token is not None else os.getenv("BITBUCKET_TOKEN")
        self.api_url = (api_url or _optional(self._config.get("api_url")) or BITBUCKET_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "bitbucket_pull_requests_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def workspaces(self) -> list[str]:
        return _strings(self._config.get("workspaces") or self._config.get("workspace"))

    @property
    def repositories(self) -> list[str]:
        return _strings(self._config.get("repositories") or self._config.get("repo_slugs"))

    @property
    def state(self) -> str | None:
        return _optional(self._config.get("state"))

    @property
    def pagelen(self) -> int:
        return _positive_int(self._config.get("pagelen"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.workspaces or not self.repositories or not self._has_auth:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for workspace in self.workspaces:
                for repository in self.repositories:
                    if len(signals) >= limit:
                        break
                    prs = await self._fetch_repository(
                        client,
                        workspace=workspace,
                        repository=repository,
                        limit=limit - len(signals),
                    )
                    signals.extend(
                        _pull_request_signal(item, workspace, repository, self.name)
                        for item in prs
                        if isinstance(item, dict)
                    )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    @property
    def _has_auth(self) -> bool:
        return bool(self.token or (self.username and self.app_password))

    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        *,
        workspace: str,
        repository: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        pull_requests: list[dict[str, Any]] = []
        url: str | None = f"{self.api_url}/repositories/{workspace}/{repository}/pullrequests"
        params: dict[str, Any] | None = {"pagelen": min(self.pagelen, limit)}
        if self.state:
            params["state"] = self.state
        while url and len(pull_requests) < limit:
            body = await self._get(client, url, params=params)
            values = body.get("values") if isinstance(body.get("values"), list) else []
            if not values:
                break
            pull_requests.extend(item for item in values if isinstance(item, dict))
            url = _optional(body.get("next"))
            params = None
            if len(values) < self.pagelen:
                break
        return pull_requests[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        auth = None
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.username and self.app_password:
            auth = httpx.BasicAuth(self.username, self.app_password)
        try:
            response = await client.get(url, headers=headers, auth=auth, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Bitbucket pull request fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


BitbucketPullRequestAdapter = BitbucketPullRequestsAdapter


def _pull_request_signal(
    pull_request: dict[str, Any],
    workspace: str,
    repository: str,
    adapter_name: str,
) -> Signal:
    author = pull_request.get("author") if isinstance(pull_request.get("author"), dict) else {}
    links = pull_request.get("links") if isinstance(pull_request.get("links"), dict) else {}
    source = pull_request.get("source") if isinstance(pull_request.get("source"), dict) else {}
    destination = (
        pull_request.get("destination") if isinstance(pull_request.get("destination"), dict) else {}
    )
    state = _text(pull_request.get("state"))
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(pull_request.get("title")) or f"{workspace}/{repository} PR",
        content=_text(pull_request.get("description"))[:1000],
        url=_link_href(links.get("html")),
        author=_text(author.get("display_name") or author.get("nickname") or author.get("username")) or None,
        published_at=_parse_dt(pull_request.get("created_on")),
        tags=sorted({"bitbucket", "pull-request", state.lower()} - {""})[:10],
        credibility=0.6,
        metadata={
            "pull_request_id": pull_request.get("id"),
            "workspace": workspace,
            "repository": repository,
            "state": pull_request.get("state"),
            "source_branch": _branch_name(source),
            "destination_branch": _branch_name(destination),
            "author": _summary(author),
            "comment_count": pull_request.get("comment_count"),
            "task_count": pull_request.get("task_count"),
            "created_on": pull_request.get("created_on"),
            "updated_on": pull_request.get("updated_on"),
            "links": links,
        },
    )


def _branch_name(value: dict[str, Any]) -> str | None:
    branch = value.get("branch") if isinstance(value.get("branch"), dict) else {}
    return _optional(branch.get("name"))


def _link_href(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("href"))
    return ""


def _summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": value.get("display_name"),
        "nickname": value.get("nickname"),
        "username": value.get("username"),
        "uuid": value.get("uuid"),
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
    text = str(value).strip() if value is not None else ""
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
