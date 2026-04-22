"""Bluesky source adapter - practitioner signals via public AppView search."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

BLUESKY_SEARCH_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"

_DEFAULT_QUERIES = ["ai", "llm", "mcp", "developer tools", "python", "typescript"]
_KEYWORD_TAGS = {
    "agent": "agent",
    "llm": "llm",
    "mcp": "mcp",
    "openai": "openai",
    "langchain": "langchain",
    "rag": "rag",
    "embedding": "embedding",
    "claude": "claude",
    "anthropic": "anthropic",
}


class BlueskyAdapter(SourceAdapter):
    """Fetch recent Bluesky posts for configured search terms."""

    @property
    def name(self) -> str:
        return "bluesky"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def domains(self) -> list[str]:
        return _normalize_strings(self._config.get("domains", []))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_uris: set[str] = set()
        queries = self.queries
        per_query = max(limit // len(queries), 5) if queries else limit

        headers = {
            "User-Agent": "max-bluesky-adapter/0.1",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for query in queries:
                if len(signals) >= limit:
                    break

                data = await self._fetch_search_results(
                    client,
                    query=query,
                    limit=min(per_query, 100),
                )
                if data is None:
                    continue

                self._append_post_signals(
                    signals,
                    data.get("posts", []),
                    query=query,
                    limit=limit,
                    seen_uris=seen_uris,
                )

        return signals[:limit]

    async def _fetch_search_results(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        limit: int,
    ) -> dict | None:
        try:
            resp = await fetch_with_retry(
                BLUESKY_SEARCH_URL,
                client,
                adapter_name=self.name,
                params={
                    "q": query,
                    "sort": "latest",
                    "limit": limit,
                },
            )
            data = resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Bluesky posts for query '%s': %s", self.name, query, e)
            return None
        except ValueError as e:
            logger.warning(
                "%s: failed to parse Bluesky JSON response for query '%s': %s",
                self.name,
                query,
                e,
            )
            return None

        if not isinstance(data, dict):
            logger.warning("%s: expected Bluesky JSON object for query '%s'", self.name, query)
            return None
        return data

    def _append_post_signals(
        self,
        signals: list[Signal],
        posts: object,
        *,
        query: str,
        limit: int,
        seen_uris: set[str],
    ) -> None:
        if not isinstance(posts, list):
            logger.warning("%s: expected Bluesky posts list for query '%s'", self.name, query)
            return

        for post in posts:
            if len(signals) >= limit:
                break
            if not isinstance(post, dict):
                continue

            try:
                uri = _string_or_none(post.get("uri"))
                if uri is None or uri in seen_uris:
                    continue

                signal = _post_to_signal(
                    post,
                    adapter_name=self.name,
                    query=query,
                    configured_domains=self.domains,
                )
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse Bluesky post: %s", self.name, e)
                continue

            seen_uris.add(uri)
            signals.append(signal)


def _post_to_signal(
    post: dict,
    *,
    adapter_name: str,
    query: str,
    configured_domains: list[str],
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

    author = post.get("author")
    if not isinstance(author, dict):
        author = {}

    author_handle = _string_or_none(author.get("handle"))
    author_did = _string_or_none(author.get("did"))
    post_url = _post_url(uri, author_handle or author_did)
    like_count = _int_or_zero(post.get("likeCount"))
    repost_count = _int_or_zero(post.get("repostCount"))
    reply_count = _int_or_zero(post.get("replyCount"))
    quote_count = _int_or_zero(post.get("quoteCount"))
    link_domains = _extract_link_domains(post)
    hashtags = _extract_hashtags(record)

    return Signal(
        source_type=SignalSourceType.FORUM,
        source_adapter=adapter_name,
        title=_title_from_text(text),
        content=text[:500],
        url=post_url,
        author=author_handle or author_did,
        published_at=_parse_datetime(record.get("createdAt") or post.get("indexedAt")),
        tags=_build_tags(
            query=query,
            text=text,
            hashtags=hashtags,
            configured_domains=configured_domains,
        ),
        credibility=_credibility(
            like_count=like_count,
            repost_count=repost_count,
            reply_count=reply_count,
            quote_count=quote_count,
        ),
        metadata={
            "uri": uri,
            "cid": _string_or_none(post.get("cid")),
            "author_did": author_did,
            "author_handle": author_handle,
            "display_name": _string_or_none(author.get("displayName")),
            "like_count": like_count,
            "repost_count": repost_count,
            "reply_count": reply_count,
            "quote_count": quote_count,
            "indexed_at": post.get("indexedAt"),
            "search_query": query,
            "hashtags": hashtags,
            "link_domains": link_domains,
            "configured_domains": configured_domains,
        },
    )


def _build_tags(
    *,
    query: str,
    text: str,
    hashtags: list[str],
    configured_domains: list[str],
) -> list[str]:
    tags: set[str] = {"bluesky"}

    query_tag = _tagify(query)
    if query_tag:
        tags.add(query_tag)

    for tag in hashtags:
        normalized = _tagify(tag)
        if normalized:
            tags.add(normalized)

    text_lower = text.lower()
    for keyword, tag in _KEYWORD_TAGS.items():
        if keyword in text_lower:
            tags.add(tag)

    for domain in configured_domains:
        normalized = _tagify(domain)
        if normalized:
            tags.add(normalized)

    return sorted(tags)[:10]


def _extract_hashtags(record: dict) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()

    for value in record.get("tags", []) if isinstance(record.get("tags"), list) else []:
        _append_tag(tags, seen, value)

    facets = record.get("facets", [])
    if isinstance(facets, list):
        for facet in facets:
            if not isinstance(facet, dict):
                continue
            features = facet.get("features", [])
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

    facets = record.get("facets", [])
    if isinstance(facets, list):
        for facet in facets:
            if not isinstance(facet, dict):
                continue
            features = facet.get("features", [])
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
    parts = uri.split("/")
    rkey = parts[-1] if parts else ""
    if author_identifier and rkey:
        return f"https://bsky.app/profile/{author_identifier}/post/{rkey}"
    return uri


def _title_from_text(text: str) -> str:
    title = " ".join(text.split())
    if len(title) <= 100:
        return title
    return f"{title[:97].rstrip()}..."


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
    parsed = urlparse(value.strip())
    host = parsed.netloc.lower()
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


def _normalize_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        term = item.strip()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


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
