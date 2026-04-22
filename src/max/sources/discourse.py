"""Discourse source adapter for public forum topic lists."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class DiscourseAdapter(SourceAdapter):
    """Fetch public Discourse forum topics from latest or category JSON lists."""

    @property
    def name(self) -> str:
        return "discourse"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def base_urls(self) -> list[str]:
        urls = [_normalize_base_url(value) for value in self._config.get("base_urls", [])]
        return [url for url in urls if url]

    @property
    def category_slugs(self) -> list[str]:
        slugs: list[str] = []
        for value in self._config.get("category_slugs", []):
            if not isinstance(value, str):
                continue
            slug = value.strip().strip("/")
            if slug:
                slugs.append(slug)
        return slugs

    @property
    def tags(self) -> list[str]:
        return self._configured_terms("tags", [])

    @property
    def max_pages(self) -> int:
        value = self._config.get("max_pages", 1)
        if isinstance(value, bool):
            return 1
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 1
        return max(parsed, 1)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()

        headers = {
            "User-Agent": "max-discourse-adapter/0.1",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
            for endpoint in self._endpoints():
                if len(signals) >= limit:
                    break

                for page in range(self.max_pages):
                    if len(signals) >= limit:
                        break

                    data = await self._fetch_topic_list(client, endpoint.url, page=page)
                    if data is None:
                        break

                    topics = _topics(data)
                    if not topics:
                        break

                    users_by_id = _users_by_id(data)
                    for topic in topics:
                        if len(signals) >= limit:
                            break
                        signal = _topic_to_signal(
                            topic,
                            base_url=endpoint.base_url,
                            forum=endpoint.forum,
                            category=endpoint.category_slug,
                            users_by_id=users_by_id,
                            adapter_name=self.name,
                            configured_tags=self.tags,
                        )
                        if signal is None or signal.url in seen:
                            continue
                        seen.add(signal.url)
                        signals.append(signal)

                    if not _has_more_topics(data):
                        break

        return signals[:limit]

    def _endpoints(self) -> list["_Endpoint"]:
        endpoints: list[_Endpoint] = []
        for base_url in self.base_urls:
            forum = _forum_name(base_url)
            if self.category_slugs:
                for slug in self.category_slugs:
                    category_path = quote(slug, safe="/-_.~")
                    endpoints.append(
                        _Endpoint(
                            base_url=base_url,
                            forum=forum,
                            category_slug=slug,
                            url=f"{base_url}/c/{category_path}.json",
                        )
                    )
            else:
                endpoints.append(
                    _Endpoint(
                        base_url=base_url,
                        forum=forum,
                        category_slug=None,
                        url=f"{base_url}/latest.json",
                    )
                )
        return endpoints

    async def _fetch_topic_list(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        page: int,
    ) -> dict | None:
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params={"page": page},
            )
            data = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Discourse topics from %s: %s", self.name, url, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse Discourse JSON from %s: %s", self.name, url, e)
            return None

        if not isinstance(data, dict):
            logger.warning("%s: expected Discourse JSON object from %s", self.name, url)
            return None
        return data


class _Endpoint:
    def __init__(
        self,
        *,
        base_url: str,
        forum: str,
        category_slug: str | None,
        url: str,
    ) -> None:
        self.base_url = base_url
        self.forum = forum
        self.category_slug = category_slug
        self.url = url


def _normalize_base_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().rstrip("/")


def _forum_name(base_url: str) -> str:
    return base_url.removeprefix("https://").removeprefix("http://").strip("/")


def _topics(data: dict) -> list[dict]:
    topic_list = data.get("topic_list")
    if not isinstance(topic_list, dict):
        return []

    topics = topic_list.get("topics", [])
    if not isinstance(topics, list):
        return []
    return [topic for topic in topics if isinstance(topic, dict)]


def _users_by_id(data: dict) -> dict[int, dict]:
    users: dict[int, dict] = {}
    for user in data.get("users", []):
        if not isinstance(user, dict):
            continue
        user_id = _int_or_none(user.get("id"))
        if user_id is not None:
            users[user_id] = user
    return users


def _has_more_topics(data: dict) -> bool:
    topic_list = data.get("topic_list")
    if not isinstance(topic_list, dict):
        return False
    return bool(topic_list.get("more_topics_url"))


def _topic_to_signal(
    topic: dict,
    *,
    base_url: str,
    forum: str,
    category: str | None,
    users_by_id: dict[int, dict],
    adapter_name: str,
    configured_tags: list[str],
) -> Signal | None:
    title = _string_or_none(topic.get("title")) or _string_or_none(topic.get("fancy_title"))
    topic_id = _int_or_none(topic.get("id"))
    if title is None or topic_id is None:
        return None

    url = _topic_url(topic, base_url=base_url, topic_id=topic_id)
    if url is None:
        return None

    reply_count = _int_or_none(topic.get("reply_count", topic.get("posts_count")))
    views = _int_or_none(topic.get("views"))
    like_count = _int_or_none(topic.get("like_count"))
    topic_category = category or _string_or_none(topic.get("category_slug")) or topic.get("category_id")
    topic_tags = _string_list(topic.get("tags"))

    metadata = {
        "forum": forum,
        "category": topic_category,
        "topic_id": topic_id,
        "slug": _string_or_none(topic.get("slug")),
    }
    if reply_count is not None:
        metadata["reply_count"] = reply_count
    if views is not None:
        metadata["views"] = views
    if like_count is not None:
        metadata["like_count"] = like_count

    return Signal(
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=title,
        content=(_string_or_none(topic.get("excerpt")) or title)[:1000],
        url=url,
        author=_topic_author(topic, users_by_id),
        published_at=_parse_datetime(topic.get("created_at")),
        tags=_dedupe_tags([*configured_tags, *topic_tags, "discourse"]),
        credibility=_credibility(reply_count=reply_count, views=views, like_count=like_count),
        metadata=metadata,
    )


def _topic_url(topic: dict, *, base_url: str, topic_id: int) -> str | None:
    topic_url = _string_or_none(topic.get("url"))
    if topic_url is not None:
        return urljoin(f"{base_url}/", topic_url)

    slug = _string_or_none(topic.get("slug"))
    if slug is None:
        return f"{base_url}/t/{topic_id}"
    return f"{base_url}/t/{quote(slug, safe='-_.~')}/{topic_id}"


def _topic_author(topic: dict, users_by_id: dict[int, dict]) -> str | None:
    posters = topic.get("posters")
    if isinstance(posters, list):
        for poster in posters:
            if not isinstance(poster, dict):
                continue
            if "Original Poster" in str(poster.get("description", "")):
                user = users_by_id.get(_int_or_none(poster.get("user_id")) or -1)
                return _user_name(user)
        for poster in posters:
            if isinstance(poster, dict):
                user = users_by_id.get(_int_or_none(poster.get("user_id")) or -1)
                name = _user_name(user)
                if name is not None:
                    return name

    return _string_or_none(topic.get("last_poster_username"))


def _user_name(user: dict | None) -> str | None:
    if not isinstance(user, dict):
        return None
    return _string_or_none(user.get("username")) or _string_or_none(user.get("name"))


def _parse_datetime(value: Any) -> datetime | None:
    text = _string_or_none(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("Failed to parse Discourse datetime: %s", value, exc_info=True)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _credibility(
    *,
    reply_count: int | None,
    views: int | None,
    like_count: int | None,
) -> float:
    score = 0.2
    if reply_count is not None:
        score += min(reply_count / 100, 0.3)
    if views is not None:
        score += min(views / 10_000, 0.3)
    if like_count is not None:
        score += min(like_count / 100, 0.2)
    return min(score, 1.0)


def _dedupe_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in tags:
        tag = value.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (_string_or_none(item) for item in value) if item is not None]


def _string_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
