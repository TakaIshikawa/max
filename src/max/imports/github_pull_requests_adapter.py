"""GitHub pull request import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


class GitHubPullRequestsAdapter(SourceAdapter):
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
            else (_optional(self._config.get("token")) or os.getenv("GITHUB_TOKEN"))
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or GITHUB_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "github_pull_requests_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def repositories(self) -> list[str]:
        return _strings(self._config.get("repositories") or self._config.get("repos"))

    @property
    def state(self) -> str:
        return _optional(self._config.get("state")) or "open"

    @property
    def labels(self) -> list[str]:
        return _strings(self._config.get("labels"))

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.repositories:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for repository in self.repositories:
                if len(signals) >= limit:
                    break
                owner_repo = _owner_repo(repository)
                if not owner_repo:
                    continue
                pulls = await self._fetch_repository(
                    client, repository=owner_repo, limit=limit - len(signals)
                )
                signals.extend(
                    _pull_request_signal(item, owner_repo, self.name)
                    for item in pulls
                    if isinstance(item, dict)
                )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        *,
        repository: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        pulls: list[dict[str, Any]] = []
        page = 1
        while len(pulls) < limit:
            page_size = min(self.per_page, limit - len(pulls))
            body = await self._get(
                client,
                f"{self.api_url}/repos/{repository}/pulls",
                params={
                    "state": self.state,
                    "per_page": page_size,
                    "page": page,
                },
            )
            if not isinstance(body, list) or not body:
                break
            filtered = [_pr for _pr in body if _matches_labels(_pr, self.labels)]
            pulls.extend(filtered)
            if len(body) < page_size:
                break
            page += 1
        return pulls[:limit]

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
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitHub pull request fetch failed for %s", url, exc_info=True)
            return []


GitHubPullRequestAdapter = GitHubPullRequestsAdapter


def _pull_request_signal(
    pull_request: dict[str, Any],
    repository: str,
    adapter_name: str,
) -> Signal:
    user = pull_request.get("user") if isinstance(pull_request.get("user"), dict) else {}
    labels = _label_names(pull_request.get("labels"))
    review_comments = _int(pull_request.get("review_comments"))
    comments = _int(pull_request.get("comments"))
    number = _int(pull_request.get("number"))
    state = _text(pull_request.get("state"))
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(pull_request.get("title")) or f"{repository} PR #{number}",
        content=_text(pull_request.get("body"))[:1000],
        url=_text(pull_request.get("html_url")),
        author=_text(user.get("login")) or None,
        published_at=_parse_dt(pull_request.get("created_at")),
        tags=sorted({"github", "pull-request", state, *labels} - {""})[:10],
        credibility=0.65,
        metadata={
            "github_pull_request_id": pull_request.get("id"),
            "repository": repository,
            "number": number,
            "state": pull_request.get("state"),
            "labels": labels,
            "draft": pull_request.get("draft"),
            "mergeable": pull_request.get("mergeable"),
            "review_count": review_comments,
            "review_comment_count": review_comments,
            "comment_count": comments,
            "created_at": pull_request.get("created_at"),
            "updated_at": pull_request.get("updated_at"),
            "closed_at": pull_request.get("closed_at"),
            "merged_at": pull_request.get("merged_at"),
            "author": _summary(user),
        },
    )


def _matches_labels(pull_request: object, required_labels: list[str]) -> bool:
    if not required_labels or not isinstance(pull_request, dict):
        return True
    existing = {label.lower() for label in _label_names(pull_request.get("labels"))}
    return all(label.lower() in existing for label in required_labels)


def _label_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        name = _text(item.get("name")) if isinstance(item, dict) else _text(item)
        if name:
            labels.append(name)
    return labels


def _owner_repo(value: str) -> str | None:
    text = value.strip()
    if "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    return f"{owner}/{repo}" if owner and repo else None


def _summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "login": value.get("login"),
        "id": value.get("id"),
        "html_url": value.get("html_url"),
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
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
