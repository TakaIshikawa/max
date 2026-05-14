"""GitHub pull request reviews import adapter."""

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


class GitHubPullRequestReviewsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        repository: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else (_optional(self._config.get("token")) or os.getenv("GITHUB_TOKEN"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or GITHUB_API).rstrip("/")
        configured_repository = repository or _optional(self._config.get("repository")) or _optional(self._config.get("repo_full_name"))
        repo_owner, repo_name = _split_repository(configured_repository)
        self.owner = owner or _optional(self._config.get("owner")) or repo_owner
        self.repo = repo or _optional(self._config.get("repo")) or repo_name
        self._client = client

    @property
    def name(self) -> str:
        return "github_pull_request_reviews_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def repositories(self) -> list[str]:
        configured = _strings(self._config.get("repositories") or self._config.get("repos"))
        if configured:
            return configured
        if self.owner and self.repo:
            return [f"{self.owner}/{self.repo}"]
        return []

    @property
    def pull_numbers(self) -> list[int]:
        values = _strings(
            self._config.get("pull_numbers")
            or self._config.get("pull_number")
            or self._config.get("pr_numbers")
            or self._config.get("pr_number")
        )
        numbers: list[int] = []
        for value in values:
            try:
                number = int(value)
            except ValueError:
                continue
            if number > 0:
                numbers.append(number)
        return numbers

    @property
    def states(self) -> set[str]:
        return {state.upper() for state in _strings(self._config.get("states") or self._config.get("state"))}

    @property
    def authors(self) -> set[str]:
        return {author.lower() for author in _strings(self._config.get("authors") or self._config.get("author"))}

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        targets = self._targets()
        if limit <= 0 or not self.token or not targets:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for repository, pull_number in targets:
                if len(signals) >= limit:
                    break
                reviews = await self._fetch_reviews(
                    client,
                    repository=repository,
                    pull_number=pull_number,
                    limit=limit - len(signals),
                )
                for review in reviews:
                    signal = _review_signal(review, repository, pull_number, self.name, seen)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    def _targets(self) -> list[tuple[str, int]]:
        configured = self._config.get("targets") or self._config.get("pull_request_targets")
        targets: list[tuple[str, int]] = []
        if isinstance(configured, list):
            for item in configured:
                target = _target_from_mapping(item)
                if target:
                    targets.append(target)
        if targets:
            return targets
        return [
            (repository, pull_number)
            for repository in self.repositories
            if _owner_repo(repository)
            for pull_number in self.pull_numbers
        ]

    async def _fetch_reviews(
        self,
        client: httpx.AsyncClient,
        *,
        repository: str,
        pull_number: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        reviews: list[dict[str, Any]] = []
        page = 1
        while len(reviews) < limit:
            page_size = min(self.per_page, limit - len(reviews))
            body = await self._get(
                client,
                f"{self.api_url}/repos/{repository}/pulls/{pull_number}/reviews",
                params={"page": page, "per_page": page_size},
            )
            if not isinstance(body, list) or not body:
                break
            for item in body:
                if isinstance(item, dict) and self._matches_filters(item):
                    reviews.append(item)
                if len(reviews) >= limit:
                    break
            if len(body) < page_size:
                break
            page += 1
        return reviews[:limit]

    def _matches_filters(self, review: dict[str, Any]) -> bool:
        if self.states and _text(review.get("state")).upper() not in self.states:
            return False
        if self.authors:
            user = review.get("user") if isinstance(review.get("user"), dict) else {}
            author = _text(user.get("login") or user.get("name") or user.get("email")).lower()
            if author not in self.authors:
                return False
        return True

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
                    "User-Agent": "max-github-pr-reviews-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("GitHub pull request reviews fetch failed for %s", url, exc_info=True)
            return []


GitHubPullRequestReviewAdapter = GitHubPullRequestReviewsAdapter


def _review_signal(
    review: dict[str, Any],
    repository: str,
    pull_number: int,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    review_id = _optional(review.get("id") or review.get("node_id") or review.get("submitted_at"))
    if not review_id:
        return None
    external_id = f"github-pr-review:{repository}:{pull_number}:{review_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    user = review.get("user") if isinstance(review.get("user"), dict) else {}
    state = _text(review.get("state"))
    body = _text(review.get("body"))
    submitted_at = review.get("submitted_at") or review.get("created_at")
    return Signal(
        id=external_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{repository} PR {pull_number} review {state or 'unknown'}",
        content=body[:1000],
        url=_review_url(review),
        author=_optional(user.get("login") or user.get("name") or user.get("email")),
        published_at=_parse_dt(submitted_at),
        tags=sorted({"github", "pull-request", "review", state.lower()} - {""})[:10],
        credibility=0.65,
        metadata={
            "github_pull_request_review_id": review.get("id"),
            "node_id": review.get("node_id"),
            "repository": repository,
            "pull_request_number": pull_number,
            "state": review.get("state"),
            "body": body,
            "commit_id": review.get("commit_id"),
            "submitted_at": review.get("submitted_at"),
            "author": {
                "login": user.get("login"),
                "id": user.get("id"),
                "node_id": user.get("node_id"),
                "type": user.get("type"),
                "html_url": user.get("html_url"),
            },
            "review_url": review.get("html_url"),
            "api_url": review.get("url"),
            "pull_request_url": review.get("pull_request_url"),
            "links": review.get("_links"),
            "raw": review,
        },
    )


def _review_url(review: dict[str, Any]) -> str:
    html_url = _text(review.get("html_url"))
    if html_url:
        return html_url
    links = review.get("_links") if isinstance(review.get("_links"), dict) else {}
    html = links.get("html") if isinstance(links.get("html"), dict) else {}
    return _text(html.get("href"))


def _target_from_mapping(value: object) -> tuple[str, int] | None:
    if not isinstance(value, dict):
        return None
    repository = _optional(
        value.get("repository") or value.get("repo_full_name") or value.get("repo")
    )
    owner = _optional(value.get("owner"))
    repo = _optional(value.get("repo_name") or value.get("name"))
    if not repository and owner and repo:
        repository = f"{owner}/{repo}"
    repository = _owner_repo(repository or "")
    if not repository:
        return None
    try:
        pull_number = int(value.get("pull_number") or value.get("pr_number") or value.get("number"))
    except (TypeError, ValueError):
        return None
    if pull_number <= 0:
        return None
    return repository, pull_number


def _split_repository(value: str | None) -> tuple[str | None, str | None]:
    if not value or "/" not in value:
        return None, None
    owner, repo = value.split("/", 1)
    return (_optional(owner), _optional(repo))


def _owner_repo(value: str) -> str | None:
    text = value.strip()
    if "/" not in text:
        return None
    owner, repo = text.split("/", 1)
    return f"{owner}/{repo}" if owner and repo else None


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
