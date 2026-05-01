"""GitLab Epics source adapter -- roadmap and planning signals."""

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


class GitLabEpicsAdapter(SourceAdapter):
    """Fetch GitLab group epics and normalize them into roadmap signals."""

    @property
    def name(self) -> str:
        return "gitlab_epics"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def groups(self) -> list[str]:
        return _string_list(self._config.get("groups"), [])

    @property
    def labels(self) -> list[str]:
        return _string_list(self._config.get("labels"), [])

    @property
    def state(self) -> str:
        state = self._config.get("state", "opened")
        if not isinstance(state, str):
            return "opened"
        normalized = state.strip().lower()
        return normalized if normalized in {"opened", "closed", "all"} else "opened"

    @property
    def gitlab_url(self) -> str:
        configured = self._config.get("gitlab_url")
        if not isinstance(configured, str) or not configured.strip():
            return GITLAB_API
        return configured.strip().rstrip("/")

    @property
    def private_token(self) -> str | None:
        configured = self._config.get("private_token")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return os.environ.get("GITLAB_TOKEN")

    @property
    def per_group_limit(self) -> int:
        return _positive_int(self._config.get("per_group_limit"), default=30)

    @property
    def timeout(self) -> float:
        value = self._config.get("timeout", 30)
        if isinstance(value, bool):
            return 30.0
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return 30.0
        return timeout if timeout > 0 else 30.0

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

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="gitlab_epics")
    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        group: str,
        *,
        page: int,
        per_page: int,
    ) -> tuple[list[dict], str]:
        url = _epics_url(self.gitlab_url, group)
        try:
            resp = await client.get(url, params=self._params(page=page, per_page=per_page))
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            _raise_http_error(e, f"epics for group: {group}", self.name)
        except (ValueError, KeyError, TypeError) as e:
            raise SourceParseError(
                f"Failed to parse epics for group: {group}",
                adapter_name=self.name,
            ) from e

        if not isinstance(data, list):
            raise SourceParseError(
                f"Unexpected epics response for group: {group}",
                adapter_name=self.name,
            )
        return data, resp.headers.get("X-Next-Page", "")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        groups = self.groups
        if limit <= 0 or not groups:
            return []

        signals: list[Signal] = []
        seen_urls: set[str] = set()
        cutoff = _cutoff(self.max_age_days)
        labels = {label.lower() for label in self.labels}

        headers = {"Accept": "application/json"}
        if self.private_token:
            headers["PRIVATE-TOKEN"] = self.private_token

        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            for group in groups:
                if len(signals) >= limit:
                    break
                await self._fetch_group(
                    client,
                    group,
                    signals=signals,
                    seen_urls=seen_urls,
                    labels=labels,
                    cutoff=cutoff,
                    limit=limit,
                )

        return signals[:limit]

    async def _fetch_group(
        self,
        client: httpx.AsyncClient,
        group: str,
        *,
        signals: list[Signal],
        seen_urls: set[str],
        labels: set[str],
        cutoff: datetime | None,
        limit: int,
    ) -> None:
        page = 1
        collected_for_group = 0
        group_cap = min(self.per_group_limit, max(limit - len(signals), 0))

        while collected_for_group < group_cap and len(signals) < limit:
            per_page = min(group_cap - collected_for_group, limit - len(signals), 100)
            if per_page <= 0:
                break

            try:
                epics, next_page = await self._fetch_page(
                    client,
                    group,
                    page=page,
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
                logger.warning("GitLab epics fetch failed for group: %s", group, exc_info=True)
                return

            before = len(signals)
            _append_epic_signals(
                signals,
                epics,
                adapter_name=self.name,
                group=group,
                limit=limit,
                group_cap=group_cap,
                group_count=collected_for_group,
                seen_urls=seen_urls,
                labels=labels,
                cutoff=cutoff,
            )
            collected_for_group += len(signals) - before

            if not next_page:
                break
            try:
                page = int(next_page)
            except ValueError:
                break

    def _params(self, *, page: int, per_page: int) -> dict[str, object]:
        params: dict[str, object] = {
            "state": self.state,
            "order_by": "updated_at",
            "sort": "desc",
            "page": page,
            "per_page": per_page,
        }
        if self.labels:
            params["labels"] = ",".join(self.labels)
        return params


def _append_epic_signals(
    signals: list[Signal],
    epics: list[dict],
    *,
    adapter_name: str,
    group: str,
    limit: int,
    group_cap: int,
    group_count: int,
    seen_urls: set[str],
    labels: set[str],
    cutoff: datetime | None,
) -> None:
    for epic in epics:
        if len(signals) >= limit or group_count >= group_cap:
            break
        if not isinstance(epic, dict) or not _matches_filters(epic, labels=labels, cutoff=cutoff):
            continue

        web_url = str(epic.get("web_url") or epic.get("url") or "").strip()
        if not web_url or web_url in seen_urls:
            continue

        title = str(epic.get("title") or "").strip()
        iid = epic.get("iid")
        if not title or iid is None:
            continue

        seen_urls.add(web_url)
        signals.append(_to_signal(epic, adapter_name=adapter_name, group=group, web_url=web_url))
        group_count += 1


def _matches_filters(epic: dict, *, labels: set[str], cutoff: datetime | None) -> bool:
    epic_labels = {label.lower() for label in _labels(epic.get("labels"))}
    if labels and labels.isdisjoint(epic_labels):
        return False

    recency_dt = _parse_dt(epic.get("updated_at") or epic.get("created_at"))
    return not (cutoff is not None and recency_dt is not None and recency_dt < cutoff)


def _to_signal(epic: dict, *, adapter_name: str, group: str, web_url: str) -> Signal:
    title = str(epic.get("title") or "").strip()
    description = str(epic.get("description") or "").strip()
    labels = _labels(epic.get("labels"))
    upvotes = _non_negative_int(epic.get("upvotes"), default=0)
    downvotes = _non_negative_int(epic.get("downvotes"), default=0)
    comments_count = _non_negative_int(
        epic.get("user_notes_count", epic.get("comments_count")),
        default=0,
    )
    author = _author(epic.get("author"))
    epic_iid = epic.get("iid")
    group_path = _group_path(epic, group, web_url)

    return Signal(
        id=_stable_id(group_path, epic_iid, epic),
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title,
        content=description[:4000] if description else title,
        url=web_url,
        author=author,
        published_at=_parse_dt(epic.get("created_at")),
        tags=_build_tags(group_path, labels, title, description),
        credibility=_credibility(upvotes, downvotes, comments_count),
        metadata={
            "gitlab_epic_id": epic.get("id"),
            "group": group,
            "group_path": group_path,
            "epic_iid": epic_iid,
            "labels": labels[:10],
            "state": epic.get("state"),
            "web_url": web_url,
            "author": author,
            "upvotes": upvotes,
            "downvotes": downvotes,
            "comments_count": comments_count,
            "created_at": epic.get("created_at"),
            "updated_at": epic.get("updated_at"),
            "signal_role": "market",
        },
    )


def _epics_url(base_url: str, group: str) -> str:
    return f"{base_url.rstrip('/')}/groups/{quote(group, safe='')}/epics"


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


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


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


def _group_path(epic: dict, configured_group: str, web_url: str) -> str:
    references = epic.get("references")
    if isinstance(references, dict):
        full = references.get("full")
        if isinstance(full, str) and "&" in full:
            return full.rsplit("&", 1)[0]

    parsed = urlparse(web_url)
    parts = [part for part in parsed.path.split("/") if part]
    if "-/epics" in parsed.path:
        marker = parts.index("-") if "-" in parts else -1
        if marker > 0:
            return "/".join(parts[:marker])
    return configured_group


def _stable_id(group_path: str, epic_iid: object, epic: dict) -> str:
    if group_path and epic_iid is not None:
        return f"gitlab_epics:{group_path}&{epic_iid}"
    fallback = epic.get("id") or epic.get("web_url")
    return f"gitlab_epics:{fallback}"


def _build_tags(group_path: str, labels: list[str], title: str, description: str) -> list[str]:
    tags: set[str] = {"gitlab", "epic", "roadmap"}
    for label in labels:
        lower = label.lower()
        if lower in {"planning", "roadmap", "strategy", "security", "performance", "ai"}:
            tags.add(lower)

    text = " ".join([group_path, title, description, " ".join(labels)]).lower()
    keyword_map = {
        "ai": ["ai", "artificial intelligence", "openai", "anthropic"],
        "agent": ["agent", "agentic"],
        "llm": ["llm", "language model", "gpt", "claude"],
        "mcp": ["mcp", "model context protocol"],
        "security": ["security", "vulnerability", "cve"],
        "integration": ["integration", "interop", "compatibility"],
        "performance": ["performance", "slow", "latency"],
        "enterprise": ["enterprise", "sso", "compliance"],
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)
    return sorted(tags)[:10]


def _credibility(upvotes: int, downvotes: int, comments_count: int) -> float:
    score = upvotes + comments_count - min(downvotes, upvotes + comments_count)
    return round(min(0.4 + (max(score, 0) / 100), 1.0), 4)


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
