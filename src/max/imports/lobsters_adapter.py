"""Lobsters import adapter for niche developer news signals.

Collects high-signal technology stories and discussion comments from the
Lobsters JSON API. Fetches hottest, newest, and tag-filtered story pages while
extracting score, comment count, submitter, tags, and canonical URLs.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlparse

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

LOBSTERS_BASE = "https://lobste.rs"
USER_AGENT = "max-lobsters-import-adapter/0.1"

_DEFAULT_PAGES = ["hottest", "newest"]
_SAFE_PATH_SEGMENT = re.compile(r"^[a-zA-Z0-9_-]+$")
_HTML_TAG = re.compile(r"<[^>]+>")


class LobstersAdapter(SourceAdapter):
    """Fetch stories and comments from Lobsters."""

    @property
    def name(self) -> str:
        return "lobsters_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def pages(self) -> list[str]:
        configured = self._config.get("pages")
        if configured is None and isinstance(self._config.get("page"), str):
            configured = [self._config["page"]]
        values = _string_list(configured, _DEFAULT_PAGES)
        pages = [page for page in values if _SAFE_PATH_SEGMENT.fullmatch(page)]
        if configured is None and not pages:
            return _DEFAULT_PAGES
        return pages

    @property
    def tags(self) -> list[str]:
        return [
            tag
            for tag in self._configured_terms("tags", [])
            if _SAFE_PATH_SEGMENT.fullmatch(tag)
        ]

    @property
    def max_pages(self) -> int:
        return _positive_int(self._config.get("max_pages"), default=1)

    @property
    def include_comments(self) -> bool:
        value = self._config.get("include_comments", True)
        return bool(value)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        signals: list[Signal] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT}) as client:
            for endpoint in self._endpoints():
                if len(signals) >= limit:
                    break

                stories = await self._fetch_story_page(client, endpoint)
                if not stories:
                    continue

                for story in stories:
                    if len(signals) >= limit:
                        break
                    if not isinstance(story, dict):
                        continue

                    story_signal = _story_to_signal(story, adapter_name=self.name, source=endpoint.source)
                    if story_signal is None or story_signal.url in seen:
                        continue

                    seen.add(story_signal.url)
                    signals.append(story_signal)

                    if self.include_comments and len(signals) < limit:
                        comments = await self._fetch_comments(client, story)
                        self._append_comment_signals(
                            signals,
                            comments,
                            story=story,
                            seen=seen,
                            limit=limit,
                        )

        return signals[:limit]

    def _endpoints(self) -> list["_Endpoint"]:
        endpoints: list[_Endpoint] = []
        story_sources = [("tag", tag) for tag in self.tags]
        story_sources.extend(("page", page) for page in self.pages)

        for source_type, source in story_sources:
            for page_number in range(1, self.max_pages + 1):
                if source_type == "tag":
                    url = f"{LOBSTERS_BASE}/t/{source}.json"
                else:
                    url = f"{LOBSTERS_BASE}/{source}.json"
                params = {"page": page_number} if page_number > 1 else None
                endpoints.append(_Endpoint(url=url, source=source, params=params))
        return endpoints

    async def _fetch_story_page(self, client: httpx.AsyncClient, endpoint: "_Endpoint") -> list[dict]:
        try:
            resp = await fetch_with_retry(
                endpoint.url,
                client,
                adapter_name=self.name,
                params=endpoint.params,
                headers={"User-Agent": USER_AGENT},
            )
            data = resp.json()
        except (AdapterFetchError, httpx.RequestError, ValueError, TypeError):
            logger.warning("Lobsters fetch failed for %s", endpoint.url, exc_info=True)
            return []

        return data if isinstance(data, list) else []

    async def _fetch_comments(self, client: httpx.AsyncClient, story: dict) -> list[dict]:
        comments = story.get("comments")
        if isinstance(comments, list):
            return [comment for comment in comments if isinstance(comment, dict)]

        comments_url = _comments_json_url(story)
        if comments_url is None:
            return []

        try:
            resp = await fetch_with_retry(
                comments_url,
                client,
                adapter_name=self.name,
                headers={"User-Agent": USER_AGENT},
            )
            data = resp.json()
        except (AdapterFetchError, httpx.RequestError, ValueError, TypeError):
            logger.warning("Lobsters comments fetch failed for %s", comments_url, exc_info=True)
            return []

        fetched_comments = data.get("comments", []) if isinstance(data, dict) else []
        return fetched_comments if isinstance(fetched_comments, list) else []

    def _append_comment_signals(
        self,
        signals: list[Signal],
        comments: list[dict],
        *,
        story: dict,
        seen: set[str],
        limit: int,
    ) -> None:
        for comment in comments:
            if len(signals) >= limit:
                break
            signal = _comment_to_signal(comment, story=story, adapter_name=self.name)
            if signal is None or signal.url in seen:
                continue
            seen.add(signal.url)
            signals.append(signal)


class _Endpoint:
    def __init__(self, *, url: str, source: str, params: dict[str, int] | None) -> None:
        self.url = url
        self.source = source
        self.params = params


def _story_to_signal(story: dict, *, adapter_name: str, source: str) -> Signal | None:
    title = _string_or_none(story.get("title"))
    if title is None:
        return None

    comments_url = _comments_url(story)
    url = _string_or_none(story.get("url")) or comments_url
    if url is None:
        return None

    score = _int_or_zero(story.get("score"))
    comment_count = _int_or_zero(story.get("comment_count", story.get("comments_count")))
    tags = _tags(story.get("tags"))
    submitter = _submitter(story)

    return Signal(
        source_type=SignalSourceType.TRENDING if source == "hottest" else SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=title,
        content=(_string_or_none(story.get("description")) or title)[:1000],
        url=url,
        author=submitter,
        published_at=_parse_datetime(story.get("created_at")),
        tags=tags,
        credibility=_credibility(score=score, comment_count=comment_count),
        metadata={
            "lobsters_type": "story",
            "short_id": _string_or_none(story.get("short_id")),
            "comments_url": comments_url,
            "score": score,
            "comment_count": comment_count,
            "submitter": submitter,
            "tags": tags,
            "source": source,
            "external_url": _string_or_none(story.get("url")),
        },
    )


def _comment_to_signal(comment: dict, *, story: dict, adapter_name: str) -> Signal | None:
    comment_id = _string_or_none(comment.get("short_id") or comment.get("id") or comment.get("comment_id"))
    body = _strip_html(
        _string_or_none(comment.get("comment") or comment.get("body") or comment.get("text")) or ""
    )
    if not comment_id or not body:
        return None

    story_title = _string_or_none(story.get("title")) or "Lobsters discussion"
    story_comments_url = _comments_url(story) or LOBSTERS_BASE
    url = f"{story_comments_url}#c_{comment_id}"
    score = _int_or_zero(comment.get("score"))

    return Signal(
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=f"Comment on {story_title}",
        content=body[:1000],
        url=url,
        author=_submitter(comment),
        published_at=_parse_datetime(comment.get("created_at")),
        tags=_tags(story.get("tags")),
        credibility=min(round(0.1 + min(score / 50, 0.4), 3), 1.0),
        metadata={
            "lobsters_type": "comment",
            "comment_id": comment_id,
            "story_short_id": _string_or_none(story.get("short_id")),
            "story_title": story_title,
            "score": score,
        },
    )


def _comments_url(story: dict) -> str | None:
    for key in ("comments_url", "short_id_url"):
        value = _string_or_none(story.get(key))
        if value is not None:
            return value
    short_id = _string_or_none(story.get("short_id"))
    return f"{LOBSTERS_BASE}/s/{short_id}" if short_id else None


def _comments_json_url(story: dict) -> str | None:
    comments_url = _comments_url(story)
    if comments_url is None:
        return None
    parsed = urlparse(comments_url)
    if parsed.netloc and parsed.netloc != "lobste.rs":
        return None
    return comments_url if comments_url.endswith(".json") else f"{comments_url}.json"


def _submitter(item: dict) -> str | None:
    submitter = item.get("submitter_user", item.get("submitter", item.get("user")))
    if isinstance(submitter, dict):
        submitter = submitter.get("username") or submitter.get("name")
    return _string_or_none(submitter)


def _tags(value: object) -> list[str]:
    tags = _string_list(value, [])
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        clean = tag.strip().lower()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)
    if "lobsters" not in seen:
        normalized.append("lobsters")
    return normalized[:10]


def _parse_datetime(value: object) -> datetime | None:
    text = _string_or_none(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _strip_html(text: str) -> str:
    return unescape(_HTML_TAG.sub(" ", text)).strip()


def _credibility(*, score: int, comment_count: int) -> float:
    return min(round(0.1 + min(score / 100, 0.7) + min(comment_count / 50, 0.2), 3), 1.0)


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _int_or_zero(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _string_list(value: object, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return list(default)
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
