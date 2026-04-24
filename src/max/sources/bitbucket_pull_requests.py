"""Bitbucket Cloud Pull Requests source adapter -- implementation review signals."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from urllib.parse import quote, urlparse

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

BITBUCKET_API = "https://api.bitbucket.org/2.0"
_DEFAULT_STATES = ["OPEN", "MERGED", "DECLINED"]
_VALID_STATES = set(_DEFAULT_STATES) | {"SUPERSEDED"}


class BitbucketPullRequestsAdapter(SourceAdapter):
    """Fetch Bitbucket Cloud pull requests from configured repositories."""

    @property
    def name(self) -> str:
        return "bitbucket_pull_requests"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def repositories(self) -> list[str]:
        repositories = _string_list(self._config.get("repositories"), [])
        workspace = _string_or_none(self._config.get("workspace"))
        repository = _string_or_none(self._config.get("repository"))
        repository_list = _string_list(self._config.get("repository_slugs"), [])

        if workspace and repository:
            repositories.append(f"{workspace}/{repository}")
        if workspace:
            repositories.extend(f"{workspace}/{slug}" for slug in repository_list)
        return _dedupe(repositories)

    @property
    def states(self) -> list[str]:
        configured = self._config.get("states", self._config.get("state"))
        values = _string_list(configured, _DEFAULT_STATES)
        if any(value.strip().lower() == "all" for value in values):
            return list(_DEFAULT_STATES)

        states: list[str] = []
        for value in values:
            state = value.strip().upper()
            if state in _VALID_STATES and state not in states:
                states.append(state)
        return states or list(_DEFAULT_STATES)

    @property
    def query(self) -> str | None:
        return _string_or_none(self._config.get("query") or self._config.get("q"))

    @property
    def token_env(self) -> str:
        configured = _string_or_none(self._config.get("token_env"))
        return configured or "BITBUCKET_TOKEN"

    @property
    def token(self) -> str | None:
        configured = self._config.get("bitbucket_token") or self._config.get("token")
        if configured:
            return str(configured)
        return os.environ.get(self.token_env)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        if limit <= 0:
            return signals

        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for repository in self.repositories:
                if len(signals) >= limit:
                    break
                try:
                    await self._append_repository_signals(
                        client,
                        repository,
                        signals=signals,
                        seen_urls=seen_urls,
                        limit=limit,
                    )
                except (AdapterFetchError, httpx.RequestError, httpx.TimeoutException, ValueError):
                    logger.warning(
                        "Bitbucket pull requests fetch failed for repository: %s",
                        repository,
                        exc_info=True,
                    )
                    continue

        return signals[:limit]

    async def _append_repository_signals(
        self,
        client: httpx.AsyncClient,
        repository: str,
        *,
        signals: list[Signal],
        seen_urls: set[str],
        limit: int,
    ) -> None:
        workspace, repo_slug = _split_repository(repository)
        if workspace is None or repo_slug is None:
            logger.warning("Skipping invalid Bitbucket repository config: %s", repository)
            return

        next_url: str | None = _pull_requests_url(workspace, repo_slug)
        params: dict[str, object] | None = self._params(limit - len(signals))

        while next_url and len(signals) < limit:
            resp = await fetch_with_retry(
                next_url,
                client,
                adapter_name=self.name,
                params=params,
            )
            params = None
            data = resp.json()
            if not isinstance(data, dict):
                raise ValueError("Unexpected Bitbucket pull requests response")

            values = data.get("values", [])
            if not isinstance(values, list):
                raise ValueError("Unexpected Bitbucket pull requests values")

            for pull_request in values:
                if len(signals) >= limit:
                    break
                if not isinstance(pull_request, dict):
                    continue
                signal = _to_signal(
                    pull_request,
                    adapter_name=self.name,
                    repository=f"{workspace}/{repo_slug}",
                    configured_repository=repository,
                )
                if signal is None or signal.url in seen_urls:
                    continue
                seen_urls.add(signal.url)
                signals.append(signal)

            next_candidate = data.get("next")
            next_url = str(next_candidate) if isinstance(next_candidate, str) and next_candidate else None

    def _params(self, remaining: int) -> dict[str, object]:
        params: dict[str, object] = {
            "pagelen": min(max(remaining, 1), 50),
            "sort": "-updated_on",
            "state": self.states,
        }
        if self.query:
            params["q"] = self.query
        return params


def _to_signal(
    pull_request: dict,
    *,
    adapter_name: str,
    repository: str,
    configured_repository: str,
) -> Signal | None:
    links = pull_request.get("links") if isinstance(pull_request.get("links"), dict) else {}
    html = links.get("html") if isinstance(links.get("html"), dict) else {}
    url = _string_or_none(html.get("href")) or _string_or_none(pull_request.get("url"))
    if url is None:
        return None

    title = _string_or_none(pull_request.get("title")) or "Bitbucket pull request"
    description = _string_or_none(pull_request.get("description")) or ""
    pr_id = pull_request.get("id")
    state = _string_or_none(pull_request.get("state"))
    author = _author(pull_request.get("author"))
    comment_count = _non_negative_int(
        pull_request.get("comment_count", pull_request.get("comments_count")),
        default=0,
    )
    task_count = _non_negative_int(
        pull_request.get("task_count", pull_request.get("tasks_count")),
        default=0,
    )
    metadata = {
        "bitbucket_pull_request_id": pr_id,
        "repository": repository,
        "configured_repository": configured_repository,
        "state": state,
        "author": author,
        "comment_count": comment_count,
        "task_count": task_count,
        "created_on": pull_request.get("created_on"),
        "updated_on": pull_request.get("updated_on"),
        "url": url,
        "signal_role": _signal_role(title, description, state),
    }

    return Signal(
        id=_stable_id(repository, pr_id, pull_request),
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=title,
        content=description[:4000] if description else title,
        url=url,
        author=author,
        published_at=_parse_dt(pull_request.get("created_on")),
        tags=_build_tags(repository, title, description, state),
        credibility=_credibility(comment_count, task_count),
        metadata=metadata,
    )


def _pull_requests_url(workspace: str, repo_slug: str) -> str:
    return (
        f"{BITBUCKET_API}/repositories/"
        f"{quote(workspace, safe='')}/{quote(repo_slug, safe='')}/pullrequests"
    )


def _split_repository(repository: str) -> tuple[str | None, str | None]:
    parts = [part for part in repository.strip().strip("/").split("/") if part]
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


def _string_list(value: object, default: list[str]) -> list[str]:
    if value is None:
        values = list(default)
    elif isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return list(default)

    normalized: list[str] = []
    for item in values:
        text = _string_or_none(item)
        if text is not None:
            normalized.append(text)
    return _dedupe(normalized)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _author(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    nickname = value.get("nickname")
    display_name = value.get("display_name")
    account_id = value.get("account_id")
    author = nickname or display_name or account_id
    return str(author) if author else None


def _non_negative_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return default


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _stable_id(repository: str, pr_id: object, pull_request: dict) -> str:
    if pr_id is not None:
        return f"bitbucket_pull_requests:{repository}#{pr_id}"
    fallback = pull_request.get("uuid") or pull_request.get("url")
    return f"bitbucket_pull_requests:{fallback}"


def _build_tags(repository: str, title: str, description: str, state: str | None) -> list[str]:
    tags: set[str] = {"bitbucket", "pull-request"}
    if state:
        tags.add(state.lower())

    path = urlparse(repository).path if "://" in repository else repository
    text = " ".join([path, title, description]).lower()
    keyword_map = {
        "ai": ["ai", "artificial intelligence", "openai", "anthropic"],
        "agent": ["agent", "agentic"],
        "llm": ["llm", "language model", "gpt", "claude"],
        "mcp": ["mcp", "model context protocol"],
        "security": ["security", "vulnerability", "cve"],
        "python": ["python"],
        "integration": ["integration", "interop", "compatibility"],
        "performance": ["performance", "slow", "latency"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)
    return sorted(tags)[:10]


def _signal_role(title: str, description: str, state: str | None) -> str:
    text = " ".join([title, description, state or ""]).lower()
    if any(term in text for term in ["bug", "fix", "failing", "regression", "broken", "error", "declined"]):
        return "problem"
    if any(term in text for term in ["feature", "enhancement", "add support", "implement", "merged"]):
        return "solution"
    if any(term in text for term in ["roadmap", "adoption", "pricing", "market"]):
        return "market"
    return "problem"


def _credibility(comment_count: int, task_count: int) -> float:
    return min(0.35 + ((comment_count + task_count) / 100), 1.0)
