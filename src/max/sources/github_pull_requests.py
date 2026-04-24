"""GitHub Pull Requests source adapter -- implementation signals from PR threads."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from max.sources.base import SourceAdapter
from max.sources.errors import (
    SourceAuthError,
    SourceParseError,
    SourceRateLimitError,
    SourceTransientError,
)
from max.sources.retry import with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

_DEFAULT_QUERIES = [
    '"ai agent" is:pr',
    '"llm" is:pr',
    '"mcp server" is:pr',
]


class GitHubPullRequestsAdapter(SourceAdapter):
    """Fetch GitHub pull requests and normalize them into forum signals."""

    @property
    def name(self) -> str:
        return "github_pull_requests"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def queries(self) -> list[str]:
        return _string_list(self._config.get("queries"), _DEFAULT_QUERIES)

    @property
    def repositories(self) -> list[str]:
        return _string_list(self._config.get("repositories"), [])

    @property
    def labels(self) -> list[str]:
        return _string_list(self._config.get("labels"), [])

    @property
    def state(self) -> str:
        state = self._config.get("state", "open")
        if not isinstance(state, str):
            return "open"
        normalized = state.strip().lower()
        return normalized if normalized in {"open", "closed", "all"} else "open"

    @property
    def min_comments(self) -> int:
        return _non_negative_int(self._config.get("min_comments"), default=0)

    @property
    def max_age_days(self) -> int | None:
        value = self._config.get("max_age_days")
        if value is None or isinstance(value, bool):
            return None
        try:
            days = int(value)
        except (TypeError, ValueError):
            return None
        return days if days > 0 else None

    @property
    def token_env(self) -> str:
        configured = self._config.get("token_env")
        return configured.strip() if isinstance(configured, str) and configured.strip() else "GITHUB_TOKEN"

    @property
    def token(self) -> str | None:
        configured = self._config.get("github_token") or self._config.get("token")
        if configured:
            return str(configured)
        return os.environ.get(self.token_env)

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_pull_requests")
    async def _fetch_repository(
        self,
        client: httpx.AsyncClient,
        repo: str,
        *,
        per_page: int,
    ) -> list[dict]:
        try:
            resp = await client.get(
                f"{GITHUB_API}/repos/{repo}/pulls",
                params={
                    "state": self.state,
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": per_page,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            _raise_http_error(e, f"pull requests for repository: {repo}", self.name)
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse pull requests for repository: {repo}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, list):
            raise SourceParseError(
                f"Unexpected pull requests response for repository: {repo}",
                adapter_name=self.name,
            )
        return data

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="github_pull_requests")
    async def _fetch_query(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        per_page: int,
    ) -> list[dict]:
        try:
            resp = await client.get(
                f"{GITHUB_API}/search/issues",
                params={
                    "q": _pr_query(query, self.state),
                    "sort": "updated",
                    "order": "desc",
                    "per_page": per_page,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            _raise_http_error(e, f"pull request search query: {query}", self.name)
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse pull request search response for query: {query}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, dict) or not isinstance(data.get("items", []), list):
            raise SourceParseError(
                f"Unexpected pull request search response for query: {query}",
                adapter_name=self.name,
            )
        return data.get("items", [])

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        labels = {label.lower() for label in self.labels}
        cutoff = _cutoff(self.max_age_days)
        scopes = len(self.repositories) + len(self.queries)
        per_page = min(max(limit // max(scopes, 1), 5), 100)

        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for repo in self.repositories:
                if len(signals) >= limit:
                    break
                try:
                    pulls = await self._fetch_repository(client, repo, per_page=per_page)
                except (SourceRateLimitError, SourceAuthError):
                    raise
                except (
                    SourceTransientError,
                    SourceParseError,
                    httpx.RequestError,
                    httpx.TimeoutException,
                ):
                    logger.warning("GitHub pull requests fetch failed for repo: %s", repo, exc_info=True)
                    continue

                _append_pull_signals(
                    signals,
                    pulls,
                    adapter_name=self.name,
                    repo_hint=repo,
                    origin_key="repository",
                    origin_value=repo,
                    limit=limit,
                    seen_urls=seen_urls,
                    labels=labels,
                    min_comments=self.min_comments,
                    cutoff=cutoff,
                )

            for query in self.queries:
                if len(signals) >= limit:
                    break
                try:
                    pulls = await self._fetch_query(client, query, per_page=per_page)
                except (SourceRateLimitError, SourceAuthError):
                    raise
                except (
                    SourceTransientError,
                    SourceParseError,
                    httpx.RequestError,
                    httpx.TimeoutException,
                ):
                    logger.warning("GitHub pull request search failed for query: %s", query, exc_info=True)
                    continue

                _append_pull_signals(
                    signals,
                    pulls,
                    adapter_name=self.name,
                    repo_hint="",
                    origin_key="search_query",
                    origin_value=query,
                    limit=limit,
                    seen_urls=seen_urls,
                    labels=labels,
                    min_comments=self.min_comments,
                    cutoff=cutoff,
                )

        return signals[:limit]


def _append_pull_signals(
    signals: list[Signal],
    pulls: list[dict],
    *,
    adapter_name: str,
    repo_hint: str,
    origin_key: str,
    origin_value: str,
    limit: int,
    seen_urls: set[str],
    labels: set[str],
    min_comments: int,
    cutoff: datetime | None,
) -> None:
    for pull in pulls:
        if len(signals) >= limit:
            break
        if not isinstance(pull, dict) or not _matches_filters(
            pull,
            labels=labels,
            min_comments=min_comments,
            cutoff=cutoff,
        ):
            continue

        html_url = str(pull.get("html_url") or "")
        if not html_url or html_url in seen_urls:
            continue
        seen_urls.add(html_url)

        signals.append(_to_signal(pull, adapter_name, repo_hint, origin_key, origin_value))


def _matches_filters(
    pull: dict,
    *,
    labels: set[str],
    min_comments: int,
    cutoff: datetime | None,
) -> bool:
    if "pull_request" in pull and not pull.get("pull_request"):
        return False

    if _comments_count(pull) < min_comments:
        return False

    pull_labels = {label.lower() for label in _labels(pull)}
    if labels and labels.isdisjoint(pull_labels):
        return False

    recency_dt = _parse_dt(pull.get("updated_at") or pull.get("created_at"))
    return not (cutoff is not None and recency_dt is not None and recency_dt < cutoff)


def _to_signal(
    pull: dict,
    adapter_name: str,
    repo_hint: str,
    origin_key: str,
    origin_value: str,
) -> Signal:
    title = str(pull.get("title") or "").strip() or "GitHub pull request"
    body = str(pull.get("body") or "").strip()
    labels = _labels(pull)
    comments = _comments_count(pull)
    repo = _repository(pull, repo_hint)
    number = pull.get("number")
    role = _signal_role(labels, title, body)
    metadata = {
        "github_pull_request_id": pull.get("id"),
        "repository": repo,
        "number": number,
        "state": pull.get("state"),
        "labels": labels[:10],
        "comments": comments,
        "review_comments": _non_negative_int(pull.get("review_comments"), default=0),
        "commits": _non_negative_int(pull.get("commits"), default=0),
        "additions": _optional_int(pull.get("additions")),
        "deletions": _optional_int(pull.get("deletions")),
        "changed_files": _optional_int(pull.get("changed_files")),
        "merged_at": pull.get("merged_at"),
        "created_at": pull.get("created_at"),
        "updated_at": pull.get("updated_at"),
        "signal_role": role,
        origin_key: origin_value,
    }

    return Signal(
        id=_stable_id(repo, number, pull),
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=title,
        content=body[:4000] if body else title,
        url=str(pull.get("html_url") or ""),
        author=_author(pull),
        published_at=_parse_dt(pull.get("created_at")),
        tags=_build_tags(repo, labels, title, body),
        credibility=_credibility(comments, metadata["review_comments"], metadata["commits"]),
        metadata=metadata,
    )


def _string_list(value: object, default: list[str]) -> list[str]:
    if value is None:
        values = list(default)
    elif isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return list(default)

    seen: set[str] = set()
    normalized: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _pr_query(query: str, state: str) -> str:
    parts = [query.strip()]
    lower = query.lower()
    if "is:pr" not in lower and "type:pr" not in lower:
        parts.append("is:pr")
    if state != "all" and "state:" not in lower and "is:open" not in lower and "is:closed" not in lower:
        parts.append(f"is:{state}")
    return " ".join(part for part in parts if part)


def _labels(pull: dict) -> list[str]:
    values = pull.get("labels") or []
    labels: list[str] = []
    if not isinstance(values, list):
        return labels
    for label in values:
        if isinstance(label, dict):
            name = str(label.get("name") or "").strip()
        else:
            name = str(label or "").strip()
        if name:
            labels.append(name)
    return labels


def _repository(pull: dict, repo_hint: str) -> str:
    repository_url = str(pull.get("repository_url") or "")
    if repository_url:
        parts = repository_url.rstrip("/").split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"
    return repo_hint or _extract_repo(str(pull.get("html_url") or ""))


def _extract_repo(html_url: str) -> str:
    parts = html_url.split("/")
    try:
        idx = parts.index("github.com")
        return f"{parts[idx + 1]}/{parts[idx + 2]}"
    except (ValueError, IndexError):
        return ""


def _author(pull: dict) -> str | None:
    user = pull.get("user")
    if isinstance(user, dict):
        login = user.get("login")
        return str(login) if login else None
    return None


def _comments_count(pull: dict) -> int:
    return _non_negative_int(pull.get("comments"), default=0)


def _non_negative_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return default


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cutoff(max_age_days: int | None) -> datetime | None:
    if max_age_days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _stable_id(repo: str, number: object, pull: dict) -> str:
    if repo and number is not None:
        return f"github_pull_requests:{repo}#{number}"
    fallback = pull.get("node_id") or pull.get("id") or pull.get("html_url")
    return f"github_pull_requests:{fallback}"


def _build_tags(repo: str, labels: list[str], title: str, body: str) -> list[str]:
    tags: set[str] = {"github", "pull-request"}
    for label in labels:
        lower = label.lower()
        if lower in {"bug", "enhancement", "documentation", "security", "performance"}:
            tags.add("docs" if lower == "documentation" else lower)

    text = " ".join([repo, title, body, " ".join(labels)]).lower()
    keyword_map = {
        "ai": ["ai", "artificial intelligence", "openai", "anthropic"],
        "agent": ["agent", "agentic"],
        "llm": ["llm", "language model", "gpt", "claude"],
        "mcp": ["mcp", "model context protocol"],
        "security": ["security", "vulnerability", "cve"],
        "typescript": ["typescript", "javascript", "vercel/ai"],
        "python": ["python"],
        "integration": ["integration", "interop", "compatibility"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)

    return sorted(tags)[:10]


def _signal_role(labels: list[str], title: str, body: str) -> str:
    text = " ".join([title, body, " ".join(labels)]).lower()
    if any(term in text for term in ["bug", "fix", "failing", "regression", "broken", "error"]):
        return "problem"
    if any(term in text for term in ["feature", "enhancement", "add support", "implement", "solution"]):
        return "solution"
    if any(term in text for term in ["roadmap", "adoption", "pricing", "market"]):
        return "market"
    return "problem"


def _credibility(comments: int, review_comments: int, commits: int) -> float:
    return min(0.35 + ((comments + review_comments + commits) / 100), 1.0)


def _raise_http_error(error: httpx.HTTPStatusError, context: str, adapter_name: str) -> None:
    status = error.response.status_code
    if status == 429 or _is_github_rate_limit(error.response):
        retry_after = error.response.headers.get("Retry-After")
        retry_seconds = float(retry_after) if retry_after else None
        raise SourceRateLimitError(
            f"Rate limit exceeded for {context}",
            adapter_name=adapter_name,
            retry_after=retry_seconds,
        ) from error
    if status in (401, 403):
        raise SourceAuthError(
            f"Authentication failed (HTTP {status}) for {context}",
            adapter_name=adapter_name,
        ) from error
    if 500 <= status < 600:
        raise SourceTransientError(
            f"Server error (HTTP {status}) for {context}",
            adapter_name=adapter_name,
        ) from error
    raise SourceTransientError(
        f"HTTP {status} for {context}",
        adapter_name=adapter_name,
    ) from error


def _is_github_rate_limit(response: httpx.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    return response.status_code == 403 and remaining == "0"
