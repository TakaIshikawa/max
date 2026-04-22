"""Lobsters source adapter - developer ecosystem forum signals."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

LOBSTERS_BASE = "https://lobste.rs"

_DEFAULT_PAGE = "newest"
_TRENDING_PAGES = {"hottest", "active"}
_SAFE_PATH_SEGMENT = re.compile(r"^[a-zA-Z0-9_-]+$")


class LobstersAdapter(SourceAdapter):
    """Fetch developer forum signals from Lobsters JSON pages."""

    @property
    def name(self) -> str:
        return "lobsters"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def tags(self) -> list[str]:
        return self._configured_terms("tags", [])

    @property
    def page(self) -> str:
        value = self._config.get("page", _DEFAULT_PAGE)
        if not isinstance(value, str) or not value.strip():
            return _DEFAULT_PAGE
        page = value.strip()
        if not _SAFE_PATH_SEGMENT.fullmatch(page):
            return _DEFAULT_PAGE
        return page

    @property
    def configured_limit(self) -> int | None:
        value = self._config.get("limit")
        if isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = self.configured_limit or limit
        signals: list[Signal] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for url, context in self._endpoints():
                if len(signals) >= effective_limit:
                    break

                data = await self._fetch_json(
                    client,
                    url,
                    context=context,
                )
                if data is None:
                    continue

                self._append_story_signals(
                    signals,
                    data,
                    limit=effective_limit,
                    seen=seen,
                )

        return signals[:effective_limit]

    def _endpoints(self) -> list[tuple[str, str]]:
        tags = [tag for tag in self.tags if _SAFE_PATH_SEGMENT.fullmatch(tag)]
        if tags:
            return [
                (f"{LOBSTERS_BASE}/t/{tag}.json", f"tag '{tag}'")
                for tag in tags
            ]
        return [(f"{LOBSTERS_BASE}/{self.page}.json", f"page '{self.page}'")]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
    ) -> list[dict] | None:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                headers={"User-Agent": "max-lobsters-adapter/0.1"},
            )
            data = resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Lobsters stories for %s: %s", self.name, context, e)
            return None
        except ValueError as e:
            logger.warning(
                "%s: failed to parse Lobsters JSON response for %s: %s",
                self.name,
                context,
                e,
            )
            return None

        if not isinstance(data, list):
            logger.warning("%s: expected Lobsters JSON list for %s", self.name, context)
            return None
        return data

    def _append_story_signals(
        self,
        signals: list[Signal],
        stories: list[dict],
        *,
        limit: int,
        seen: set[str],
    ) -> None:
        for story in stories:
            if len(signals) >= limit:
                break
            if not isinstance(story, dict):
                continue

            try:
                key = _story_key(story)
                if key in seen:
                    continue
                signal = _story_to_signal(story, adapter_name=self.name, page=self.page)
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse Lobsters story: %s", self.name, e)
                continue

            seen.add(key)
            signals.append(signal)


def _story_to_signal(story: dict, *, adapter_name: str, page: str) -> Signal:
    title = _string_or_none(story.get("title"))
    if title is None:
        raise ValueError("missing title")

    short_id = _string_or_none(story.get("short_id"))
    comments_url = _comments_url(story)
    url = _string_or_none(story.get("url")) or comments_url
    if url is None:
        raise ValueError("missing url")

    score = _int_or_zero(story.get("score"))
    comment_count = _int_or_zero(
        story.get("comment_count", story.get("comments_count"))
    )
    tags = _tags(story.get("tags"))
    published_at = _parse_datetime(story.get("created_at"))

    return Signal(
        source_type=_source_type_for_page(page),
        source_adapter=adapter_name,
        title=title,
        content=(_string_or_none(story.get("description")) or title)[:500],
        url=url,
        author=_submitter(story),
        published_at=published_at,
        tags=tags,
        credibility=_credibility(score=score, comment_count=comment_count),
        metadata={
            "short_id": short_id,
            "comments_url": comments_url,
            "submitter": _submitter(story),
            "score": score,
            "comment_count": comment_count,
            "tags": tags,
            "created_at": story.get("created_at"),
            "page": page,
        },
    )


def _source_type_for_page(page: str) -> SignalSourceType:
    if page in _TRENDING_PAGES:
        return SignalSourceType.TRENDING
    return SignalSourceType.FORUM


def _story_key(story: dict) -> str:
    for key in ("short_id", "comments_url", "short_id_url", "url"):
        value = _string_or_none(story.get(key))
        if value is not None:
            return value
    raise ValueError("missing story identifier")


def _comments_url(story: dict) -> str | None:
    comments_url = _string_or_none(story.get("comments_url"))
    if comments_url is not None:
        return comments_url

    short_id_url = _string_or_none(story.get("short_id_url"))
    if short_id_url is not None:
        return short_id_url

    short_id = _string_or_none(story.get("short_id"))
    if short_id is not None:
        return f"{LOBSTERS_BASE}/s/{short_id}"

    return None


def _submitter(story: dict) -> str | None:
    submitter = story.get("submitter_user", story.get("submitter"))
    if isinstance(submitter, dict):
        submitter = submitter.get("username") or submitter.get("name")
    return _string_or_none(submitter)


def _tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["lobsters"]

    tags: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        tag = item.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)

    if "lobsters" not in seen:
        tags.append("lobsters")
    return tags[:10]


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _credibility(*, score: int, comment_count: int) -> float:
    score_component = min(score / 100, 0.7)
    comment_component = min(comment_count / 50, 0.2)
    return min(round(0.1 + score_component + comment_component, 3), 1.0)


def _int_or_zero(value: object) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
