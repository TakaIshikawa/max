"""GitLab Merge Requests source adapter -- implementation review signals."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlparse

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

GITLAB_API = "https://gitlab.com/api/v4"

_DEFAULT_QUERIES = [
    "ai agent",
    "llm",
    "mcp server",
]


class GitLabMergeRequestsAdapter(SourceAdapter):
    """Fetch GitLab merge requests and normalize them into forum signals."""

    @property
    def name(self) -> str:
        return "gitlab_merge_requests"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def project_ids(self) -> list[str]:
        return _string_list(self._config.get("project_ids"), [])

    @property
    def queries(self) -> list[str]:
        return _string_list(self._config.get("queries"), _DEFAULT_QUERIES)

    @property
    def labels(self) -> list[str]:
        return _string_list(self._config.get("labels"), [])

    @property
    def state(self) -> str:
        state = self._config.get("state", "opened")
        if not isinstance(state, str):
            return "opened"
        normalized = state.strip().lower()
        return normalized if normalized in {"opened", "closed", "locked", "merged", "all"} else "opened"

    @property
    def min_upvotes(self) -> int:
        return _non_negative_int(self._config.get("min_upvotes"), default=0)

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
    def gitlab_base_url(self) -> str:
        configured = self._config.get("gitlab_base_url")
        if not isinstance(configured, str) or not configured.strip():
            return GITLAB_API
        return configured.strip().rstrip("/")

    @property
    def token_env(self) -> str:
        configured = self._config.get("token_env")
        return configured.strip() if isinstance(configured, str) and configured.strip() else "GITLAB_TOKEN"

    @property
    def token(self) -> str | None:
        return os.environ.get(self.token_env)

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="gitlab_merge_requests")
    async def _fetch_project(
        self,
        client: httpx.AsyncClient,
        project_id: str,
        *,
        per_page: int,
    ) -> list[dict]:
        url = _merge_requests_url(self.gitlab_base_url, project_id)
        try:
            resp = await client.get(url, params=self._params(per_page=per_page))
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            _raise_http_error(e, f"merge requests for project: {project_id}", self.name)
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse merge requests for project: {project_id}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, list):
            raise SourceParseError(
                f"Unexpected merge requests response for project: {project_id}",
                adapter_name=self.name,
            )
        return data

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="gitlab_merge_requests")
    async def _fetch_query(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        per_page: int,
    ) -> list[dict]:
        url = _merge_requests_url(self.gitlab_base_url, None)
        try:
            resp = await client.get(
                url,
                params={
                    **self._params(per_page=per_page),
                    "search": query,
                    "scope": "all",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            _raise_http_error(e, f"merge request search query: {query}", self.name)
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse merge request search response for query: {query}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, list):
            raise SourceParseError(
                f"Unexpected merge request search response for query: {query}",
                adapter_name=self.name,
            )
        return data

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_urls: set[str] = set()
        labels = {label.lower() for label in self.labels}
        cutoff = _cutoff(self.max_age_days)
        scopes = len(self.project_ids) + len(self.queries)
        if scopes == 0:
            return []
        per_page = min(max(limit // max(scopes, 1), 5), 100)

        headers = {"Accept": "application/json"}
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for project_id in self.project_ids:
                if len(signals) >= limit:
                    break
                try:
                    merge_requests = await self._fetch_project(
                        client,
                        project_id,
                        per_page=per_page,
                    )
                except (SourceRateLimitError, SourceAuthError):
                    raise
                except (
                    SourceTransientError,
                    SourceParseError,
                    httpx.RequestError,
                    httpx.TimeoutException,
                ):
                    logger.warning(
                        "GitLab merge requests fetch failed for project: %s",
                        project_id,
                        exc_info=True,
                    )
                    continue

                _append_merge_request_signals(
                    signals,
                    merge_requests,
                    adapter_name=self.name,
                    origin_key="project_id_config",
                    origin_value=project_id,
                    limit=limit,
                    seen_urls=seen_urls,
                    labels=labels,
                    min_upvotes=self.min_upvotes,
                    cutoff=cutoff,
                )

            for query in self.queries:
                if len(signals) >= limit:
                    break
                try:
                    merge_requests = await self._fetch_query(client, query, per_page=per_page)
                except (SourceRateLimitError, SourceAuthError):
                    raise
                except (
                    SourceTransientError,
                    SourceParseError,
                    httpx.RequestError,
                    httpx.TimeoutException,
                ):
                    logger.warning(
                        "GitLab merge request search failed for query: %s",
                        query,
                        exc_info=True,
                    )
                    continue

                _append_merge_request_signals(
                    signals,
                    merge_requests,
                    adapter_name=self.name,
                    origin_key="search_query",
                    origin_value=query,
                    limit=limit,
                    seen_urls=seen_urls,
                    labels=labels,
                    min_upvotes=self.min_upvotes,
                    cutoff=cutoff,
                )

        return signals[:limit]

    def _params(self, *, per_page: int) -> dict[str, object]:
        params: dict[str, object] = {
            "state": self.state,
            "order_by": "updated_at",
            "sort": "desc",
            "per_page": per_page,
        }
        if self.labels:
            params["labels"] = ",".join(self.labels)
        return params


def _append_merge_request_signals(
    signals: list[Signal],
    merge_requests: list[dict],
    *,
    adapter_name: str,
    origin_key: str,
    origin_value: str,
    limit: int,
    seen_urls: set[str],
    labels: set[str],
    min_upvotes: int,
    cutoff: datetime | None,
) -> None:
    for merge_request in merge_requests:
        if len(signals) >= limit:
            break
        if not isinstance(merge_request, dict) or not _matches_filters(
            merge_request,
            labels=labels,
            min_upvotes=min_upvotes,
            cutoff=cutoff,
        ):
            continue

        web_url = str(merge_request.get("web_url") or "")
        if not web_url or web_url in seen_urls:
            continue
        seen_urls.add(web_url)

        signals.append(_to_signal(merge_request, adapter_name, origin_key, origin_value))


def _matches_filters(
    merge_request: dict,
    *,
    labels: set[str],
    min_upvotes: int,
    cutoff: datetime | None,
) -> bool:
    if _non_negative_int(merge_request.get("upvotes"), default=0) < min_upvotes:
        return False

    mr_labels = {label.lower() for label in _labels(merge_request.get("labels"))}
    if labels and labels.isdisjoint(mr_labels):
        return False

    recency_dt = _parse_dt(merge_request.get("updated_at") or merge_request.get("created_at"))
    return not (cutoff is not None and recency_dt is not None and recency_dt < cutoff)


def _to_signal(
    merge_request: dict,
    adapter_name: str,
    origin_key: str,
    origin_value: str,
) -> Signal:
    title = str(merge_request.get("title") or "").strip() or "GitLab merge request"
    description = str(merge_request.get("description") or "").strip()
    labels = _labels(merge_request.get("labels"))
    upvotes = _non_negative_int(merge_request.get("upvotes"), default=0)
    comments_count = _comments_count(merge_request)
    project_id = merge_request.get("project_id")
    iid = merge_request.get("iid")
    web_url = str(merge_request.get("web_url") or "")
    project_path = _project_path(merge_request, web_url)
    author = _author(merge_request.get("author"))
    metadata = {
        "gitlab_merge_request_id": merge_request.get("id"),
        "project_id": project_id,
        "project_path": project_path,
        "merge_request_iid": iid,
        "state": merge_request.get("state"),
        "labels": labels[:10],
        "author": author,
        "upvotes": upvotes,
        "comments_count": comments_count,
        "created_at": merge_request.get("created_at"),
        "updated_at": merge_request.get("updated_at"),
        "url": web_url,
        "signal_role": _signal_role(labels, title, description),
        origin_key: origin_value,
    }

    return Signal(
        id=_stable_id(project_path, project_id, iid, merge_request),
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=title,
        content=description[:4000] if description else title,
        url=web_url,
        author=author,
        published_at=_parse_dt(merge_request.get("created_at")),
        tags=_build_tags(project_path, labels, title, description),
        credibility=_credibility(upvotes, comments_count),
        metadata=metadata,
    )


def _merge_requests_url(base_url: str, project_id: str | None) -> str:
    base = base_url.rstrip("/")
    if project_id:
        return f"{base}/projects/{quote(project_id, safe='')}/merge_requests"
    return f"{base}/merge_requests"


def _string_list(value: object, default: list[str]) -> list[str]:
    if value is None:
        values = list(default)
    elif isinstance(value, (str, int)) and not isinstance(value, bool):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return list(default)

    seen: set[str] = set()
    normalized: list[str] = []
    for item in values:
        if not isinstance(item, (str, int)) or isinstance(item, bool):
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _labels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = ""
        if name:
            labels.append(name)
    return labels


def _author(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    author = value.get("username") or value.get("name")
    return str(author) if author else None


def _comments_count(merge_request: dict) -> int:
    return _non_negative_int(
        merge_request.get("user_notes_count", merge_request.get("comments_count")),
        default=0,
    )


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


def _cutoff(max_age_days: int | None) -> datetime | None:
    if max_age_days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _project_path(merge_request: dict, web_url: str) -> str:
    references = merge_request.get("references")
    if isinstance(references, dict):
        full = references.get("full")
        if isinstance(full, str) and "!" in full:
            return full.rsplit("!", 1)[0]

    parsed = urlparse(web_url)
    parts = [part for part in parsed.path.split("/") if part]
    if "-/merge_requests" in parsed.path:
        marker = parts.index("-") if "-" in parts else -1
        if marker > 0:
            return "/".join(parts[:marker])
    return ""


def _stable_id(project_path: str, project_id: object, iid: object, merge_request: dict) -> str:
    project = project_path or str(project_id or "")
    if project and iid is not None:
        return f"gitlab_merge_requests:{project}!{iid}"
    fallback = merge_request.get("id") or merge_request.get("web_url")
    return f"gitlab_merge_requests:{fallback}"


def _build_tags(project_path: str, labels: list[str], title: str, description: str) -> list[str]:
    tags: set[str] = {"gitlab", "merge-request"}
    for label in labels:
        lower = label.lower()
        if lower in {"bug", "enhancement", "documentation", "security", "performance"}:
            tags.add("docs" if lower == "documentation" else lower)

    text = " ".join([project_path, title, description, " ".join(labels)]).lower()
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


def _signal_role(labels: list[str], title: str, description: str) -> str:
    text = " ".join([title, description, " ".join(labels)]).lower()
    if any(term in text for term in ["bug", "fix", "failing", "regression", "broken", "error"]):
        return "problem"
    if any(term in text for term in ["feature", "enhancement", "add support", "implement", "solution"]):
        return "solution"
    if any(term in text for term in ["roadmap", "adoption", "pricing", "market"]):
        return "market"
    return "problem"


def _credibility(upvotes: int, comments_count: int) -> float:
    return min(0.35 + ((upvotes + comments_count) / 100), 1.0)


def _raise_http_error(error: httpx.HTTPStatusError, context: str, adapter_name: str) -> None:
    status = error.response.status_code
    if status == 429:
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
