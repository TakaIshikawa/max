"""Bluesky import adapter for public post search and actor feeds."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

BLUESKY_API_BASE = "https://public.api.bsky.app/xrpc"
BLUESKY_SEARCH_URL = f"{BLUESKY_API_BASE}/app.bsky.feed.searchPosts"
BLUESKY_ACTOR_FEED_URL = f"{BLUESKY_API_BASE}/app.bsky.feed.getAuthorFeed"

_DEFAULT_QUERIES = ["ai", "llm", "mcp", "developer tools"]
_KEYWORD_TAGS = {
    "agent": "agent",
    "llm": "llm",
    "mcp": "mcp",
    "openai": "openai",
    "rag": "rag",
    "security": "security",
    "devtools": "devtools",
}


class BlueskyAdapter(SourceAdapter):
    """Fetch public Bluesky search results and actor posts as signals."""

    @property
    def name(self) -> str:
        return "bluesky_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def queries(self) -> list[str]:
        configured = self._config.get("queries")
        if configured is None:
            configured = self._config.get("query_terms")
        values = _string_values(configured) if configured is not None else list(_DEFAULT_QUERIES)
        return _dedupe(values + _string_values(self._config.get("watchlist_terms")))

    @property
    def handles(self) -> list[str]:
        configured = self._config.get("handles")
        if configured is None:
            configured = self._config.get("actors")
        return _dedupe(_string_values(configured))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        signals: list[Signal] = []
        seen_uris: set[str] = set()
        headers = {
            "Accept": "application/json",
            "User-Agent": "max-bluesky-import-adapter/0.1",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for query in self.queries:
                if len(signals) >= limit:
                    break
                await self._fetch_search(
                    client,
                    query=query,
                    signals=signals,
                    seen_uris=seen_uris,
                    limit=limit,
                )

            for handle in self.handles:
                if len(signals) >= limit:
                    break
                await self._fetch_actor_feed(
                    client,
                    handle=handle,
                    signals=signals,
                    seen_uris=seen_uris,
                    limit=limit,
                )

        return signals[:limit]

    async def _fetch_search(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        signals: list[Signal],
        seen_uris: set[str],
        limit: int,
    ) -> None:
        data = await self._fetch_json(
            client,
            BLUESKY_SEARCH_URL,
            context=f"search query '{query}'",
            params={"q": query, "sort": "latest", "limit": min(max(limit - len(signals), 1), 100)},
        )
        self._append_posts(
            signals,
            _posts_from_response(data, key="posts"),
            seen_uris=seen_uris,
            limit=limit,
            query=query,
            actor=None,
        )

    async def _fetch_actor_feed(
        self,
        client: httpx.AsyncClient,
        *,
        handle: str,
        signals: list[Signal],
        seen_uris: set[str],
        limit: int,
    ) -> None:
        data = await self._fetch_json(
            client,
            BLUESKY_ACTOR_FEED_URL,
            context=f"actor feed '{handle}'",
            params={"actor": handle, "limit": min(max(limit - len(signals), 1), 100)},
        )
        self._append_posts(
            signals,
            _posts_from_response(data, key="feed"),
            seen_uris=seen_uris,
            limit=limit,
            query=None,
            actor=handle,
        )

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object],
    ) -> object | None:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
            )
            return resp.json()
        except Exception:
            logger.warning("%s: failed to fetch Bluesky %s", self.name, context, exc_info=True)
            return None

    def _append_posts(
        self,
        signals: list[Signal],
        posts: list[dict],
        *,
        seen_uris: set[str],
        limit: int,
        query: str | None,
        actor: str | None,
    ) -> None:
        for post in posts:
            if len(signals) >= limit:
                break
            try:
                normalized_post = _unwrap_feed_post(post)
                uri = _string_or_none(normalized_post.get("uri"))
                if uri is None or uri in seen_uris:
                    continue
                signal = _post_to_signal(
                    normalized_post,
                    adapter_name=self.name,
                    query=query,
                    actor=actor,
                )
            except (TypeError, ValueError):
                logger.warning("%s: failed to parse Bluesky post", self.name, exc_info=True)
                continue

            seen_uris.add(uri)
            signals.append(signal)


def _post_to_signal(
    post: dict,
    *,
    adapter_name: str,
    query: str | None,
    actor: str | None,
) -> Signal:
    uri = _string_or_none(post.get("uri"))
    if uri is None:
        raise ValueError("missing uri")

    record = post.get("record")
    if not isinstance(record, dict):
        raise ValueError("missing record")

    text = _string_or_none(record.get("text"))
    if text is None:
        raise ValueError("missing text")

    author = post.get("author") if isinstance(post.get("author"), dict) else {}
    author_handle = _string_or_none(author.get("handle"))
    author_did = _string_or_none(author.get("did"))
    like_count = _int_or_zero(post.get("likeCount"))
    repost_count = _int_or_zero(post.get("repostCount"))
    reply_count = _int_or_zero(post.get("replyCount"))
    quote_count = _int_or_zero(post.get("quoteCount"))
    hashtags = _extract_hashtags(record)

    return Signal(
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=_title_from_text(text),
        content=text[:1000],
        url=_post_url(uri, author_handle or author_did),
        author=author_handle or author_did,
        published_at=_parse_datetime(record.get("createdAt") or post.get("indexedAt")),
        tags=_build_tags(text=text, query=query, hashtags=hashtags),
        credibility=_credibility(
            like_count=like_count,
            repost_count=repost_count,
            reply_count=reply_count,
            quote_count=quote_count,
        ),
        metadata={
            "uri": uri,
            "cid": _string_or_none(post.get("cid")),
            "author_handle": author_handle,
            "author_did": author_did,
            "display_name": _string_or_none(author.get("displayName")),
            "like_count": like_count,
            "repost_count": repost_count,
            "reply_count": reply_count,
            "quote_count": quote_count,
            "indexed_at": post.get("indexedAt"),
            "search_query": query,
            "actor": actor,
            "hashtags": hashtags,
            "link_domains": _extract_link_domains(post),
        },
    )


def _posts_from_response(data: object, *, key: str) -> list[dict]:
    if not isinstance(data, dict):
        return []
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unwrap_feed_post(item: dict) -> dict:
    post = item.get("post")
    return post if isinstance(post, dict) else item


def _build_tags(*, text: str, query: str | None, hashtags: list[str]) -> list[str]:
    tags: set[str] = {"bluesky", "social"}
    if query:
        query_tag = _tagify(query)
        if query_tag:
            tags.add(query_tag)
    for tag in hashtags:
        normalized = _tagify(tag)
        if normalized:
            tags.add(normalized)
    lowered = text.lower()
    for keyword, tag in _KEYWORD_TAGS.items():
        if keyword in lowered:
            tags.add(tag)
    return sorted(tags)[:10]


def _extract_hashtags(record: dict) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    values = record.get("tags")
    if isinstance(values, list):
        for value in values:
            _append_tag(tags, seen, value)

    facets = record.get("facets")
    if isinstance(facets, list):
        for facet in facets:
            if not isinstance(facet, dict):
                continue
            features = facet.get("features")
            if not isinstance(features, list):
                continue
            for feature in features:
                if isinstance(feature, dict):
                    _append_tag(tags, seen, feature.get("tag"))
    return tags[:10]


def _extract_link_domains(post: dict) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    record = post.get("record") if isinstance(post.get("record"), dict) else {}
    facets = record.get("facets")
    if isinstance(facets, list):
        for facet in facets:
            if not isinstance(facet, dict):
                continue
            features = facet.get("features")
            if not isinstance(features, list):
                continue
            for feature in features:
                if isinstance(feature, dict):
                    _append_domain(domains, seen, feature.get("uri"))

    embed = post.get("embed")
    if isinstance(embed, dict):
        external = embed.get("external")
        if isinstance(external, dict):
            _append_domain(domains, seen, external.get("uri"))
    return domains[:10]


def _post_url(uri: str, author_identifier: str | None) -> str:
    rkey = uri.split("/")[-1]
    if author_identifier and rkey:
        return f"https://bsky.app/profile/{author_identifier}/post/{rkey}"
    return uri


def _title_from_text(text: str) -> str:
    title = " ".join(text.split())
    return title if len(title) <= 120 else f"{title[:117].rstrip()}..."


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


def _credibility(
    *,
    like_count: int,
    repost_count: int,
    reply_count: int,
    quote_count: int,
) -> float:
    engagement = like_count + (repost_count * 2) + reply_count + quote_count
    return min(round(0.1 + (engagement / 100), 3), 1.0)


def _append_tag(tags: list[str], seen: set[str], value: object) -> None:
    tag = _tagify(value)
    if tag and tag not in seen:
        seen.add(tag)
        tags.append(tag)


def _append_domain(domains: list[str], seen: set[str], value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    host = urlparse(value.strip()).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host and host not in seen:
        seen.add(host)
        domains.append(host)


def _tagify(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().lstrip("#").replace(" ", "-")
    return normalized or None


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _int_or_zero(value: object) -> int:
    try:
        if value is None:
            return 0
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
