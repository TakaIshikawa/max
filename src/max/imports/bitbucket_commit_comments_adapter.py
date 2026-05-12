"""Bitbucket commit comments import adapter."""

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


class BitbucketCommitCommentsImportAdapter(SourceAdapter):
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
        self.username = (
            username
            if username is not None
            else (_optional(self._config.get("username")) or os.getenv("BITBUCKET_USERNAME"))
        )
        self.app_password = (
            app_password
            if app_password is not None
            else (
                _optional(self._config.get("app_password"))
                or _optional(self._config.get("password"))
                or os.getenv("BITBUCKET_APP_PASSWORD")
            )
        )
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("token"))
                or _optional(self._config.get("bearer_token"))
                or os.getenv("BITBUCKET_TOKEN")
                or os.getenv("BITBUCKET_BEARER_TOKEN")
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or BITBUCKET_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "bitbucket_commit_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def workspace(self) -> str | None:
        return _optional(self._config.get("workspace"))

    @property
    def repositories(self) -> list[str]:
        return _strings(
            self._config.get("repositories")
            or self._config.get("repository")
            or self._config.get("repo_slugs")
            or self._config.get("repo_slug")
        )

    @property
    def commit_hashes(self) -> list[str]:
        return _strings(
            self._config.get("commit_hashes")
            or self._config.get("commits")
            or self._config.get("commit_hash")
            or self._config.get("hash")
        )

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("pagelen"),
            default=30,
            maximum=100,
        )

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        targets = self._targets()
        if limit <= 0 or not targets or not self._has_auth:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for target in targets:
                if len(signals) >= limit:
                    break
                comments = await self._fetch_commit_comments(
                    client,
                    workspace=target["workspace"],
                    repository=target["repository"],
                    commit_hash=target["commit_hash"],
                    limit=limit - len(signals),
                )
                for comment in comments:
                    signal = _comment_signal(
                        comment,
                        workspace=target["workspace"],
                        repository=target["repository"],
                        commit_hash=target["commit_hash"],
                        adapter_name=self.name,
                        seen=seen,
                    )
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    @property
    def _has_auth(self) -> bool:
        return bool(self.token or (self.username and self.app_password))

    def _targets(self) -> list[dict[str, str]]:
        configured = self._config.get("targets") or self._config.get("commit_targets")
        targets: list[dict[str, str]] = []
        if isinstance(configured, list):
            for item in configured:
                target = _target_from_mapping(item, default_workspace=self.workspace)
                if target:
                    targets.append(target)
        if targets:
            return targets

        workspace = self.workspace
        if not workspace:
            return []
        return [
            {"workspace": workspace, "repository": repository, "commit_hash": commit_hash}
            for repository in self.repositories
            for commit_hash in self.commit_hashes
        ]

    async def _fetch_commit_comments(
        self,
        client: httpx.AsyncClient,
        *,
        workspace: str,
        repository: str,
        commit_hash: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        url: str | None = (
            f"{self.api_url}/repositories/{workspace}/{repository}/commit/{commit_hash}/comments"
        )
        params: dict[str, Any] | None = {"pagelen": min(self.page_size, limit)}
        while url and len(comments) < limit:
            body = await self._get(client, url, params=params)
            values = body.get("values") if isinstance(body.get("values"), list) else []
            if not values:
                break
            comments.extend(item for item in values if isinstance(item, dict))
            url = _optional(body.get("next"))
            params = None
        return comments[:limit]

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
            logger.warning("Bitbucket commit comment fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


BitbucketCommitCommentsAdapter = BitbucketCommitCommentsImportAdapter


def _comment_signal(
    comment: dict[str, Any],
    *,
    workspace: str,
    repository: str,
    commit_hash: str,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    comment_id = _optional(comment.get("id"))
    if not comment_id:
        return None
    external_id = f"bitbucket-commit-comment:{workspace}:{repository}:{commit_hash}:{comment_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    content = comment.get("content") if isinstance(comment.get("content"), dict) else {}
    links = comment.get("links") if isinstance(comment.get("links"), dict) else {}
    inline = comment.get("inline") if isinstance(comment.get("inline"), dict) else {}
    raw_content = _text(content.get("raw")) or _text(content.get("html"))

    return Signal(
        id=external_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"Bitbucket commit {commit_hash[:12]} comment",
        content=raw_content[:1000],
        url=_link_href(links.get("html")),
        author=_text(user.get("display_name") or user.get("nickname") or user.get("username")) or None,
        published_at=_parse_dt(comment.get("created_on")),
        tags=sorted({"bitbucket", "commit-comment", "code-review"} - {""})[:10],
        credibility=0.6,
        metadata={
            "comment_id": comment.get("id"),
            "workspace": workspace,
            "repository": repository,
            "commit_hash": commit_hash,
            "author": _summary(user),
            "content": content,
            "inline": inline,
            "parent_id": comment.get("parent", {}).get("id") if isinstance(comment.get("parent"), dict) else None,
            "created_on": comment.get("created_on"),
            "updated_on": comment.get("updated_on"),
            "links": links,
            "raw": comment,
        },
    )


def _target_from_mapping(value: object, *, default_workspace: str | None) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    workspace = _optional(value.get("workspace")) or default_workspace
    repository = _optional(
        value.get("repository") or value.get("repo") or value.get("repo_slug") or value.get("slug")
    )
    commit_hash = _optional(
        value.get("commit_hash") or value.get("commit") or value.get("hash") or value.get("commit_id")
    )
    if not (workspace and repository and commit_hash):
        return None
    return {"workspace": workspace, "repository": repository, "commit_hash": commit_hash}


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
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
