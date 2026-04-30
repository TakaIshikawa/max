"""Figma Community source adapter."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

import httpx

from max.sources.base import AdapterCircuitOpenError, AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

FIGMA_COMMUNITY_BASE_URL = "https://www.figma.com"
FIGMA_COMMUNITY_SEARCH_URL = f"{FIGMA_COMMUNITY_BASE_URL}/community/api/search/resources"

_DEFAULT_QUERIES = ["developer tools", "design system", "ai", "workflow"]
_DEFAULT_SORT = "popular"
_RESOURCE_TYPES = ("plugin", "file")


class FigmaCommunityAdapter(SourceAdapter):
    """Fetch Figma Community plugin and file marketplace signals."""

    @property
    def name(self) -> str:
        return "figma_community"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKETPLACE.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def tags(self) -> list[str]:
        return _string_list(self._config.get("tags"))

    @property
    def sort(self) -> str:
        return _string_or_none(self._config.get("sort")) or _DEFAULT_SORT

    @property
    def include_plugins(self) -> bool:
        return _bool_config(self._config.get("include_plugins"), default=True)

    @property
    def include_files(self) -> bool:
        return _bool_config(self._config.get("include_files"), default=True)

    @property
    def max_items(self) -> int | None:
        value = _int_or_none(self._config.get("max_items"))
        return value if value is not None and value > 0 else None

    @property
    def resource_types(self) -> list[str]:
        values: list[str] = []
        if self.include_plugins:
            values.append("plugin")
        if self.include_files:
            values.append("file")
        return values

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.max_items) if self.max_items is not None else limit
        if effective_limit <= 0 or not self.resource_types:
            return []

        signals: list[Signal] = []
        seen_resources: set[str] = set()

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for query in self.queries:
                if len(signals) >= effective_limit:
                    break
                for resource_type in self.resource_types:
                    if len(signals) >= effective_limit:
                        break

                    data = await self._fetch_json(
                        client,
                        context=f"{resource_type} query '{query}'",
                        params={
                            "query": query,
                            "resource_type": resource_type,
                            "sort": self.sort,
                            "limit": min(100, max(1, effective_limit - len(signals))),
                        },
                    )
                    if data is None:
                        continue

                    self._append_resource_signals(
                        signals,
                        _extract_resources(data, default_resource_type=resource_type),
                        limit=effective_limit,
                        seen_resources=seen_resources,
                        search_query=query,
                    )

        return signals[:effective_limit]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | None:
        try:
            resp = await fetch_with_retry(
                FIGMA_COMMUNITY_SEARCH_URL,
                client,
                adapter_name=self.name,
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "max-figma-community-adapter/0.1",
                },
            )
            data = resp.json()
            return data if isinstance(data, dict) else None
        except (AdapterCircuitOpenError, AdapterFetchError) as e:
            logger.warning("%s: failed to fetch Figma Community data for %s: %s", self.name, context, e)
        except (ValueError, httpx.RequestError) as e:
            logger.warning("%s: failed to parse Figma Community response for %s: %s", self.name, context, e)
        return None

    def _append_resource_signals(
        self,
        signals: list[Signal],
        resources: list[dict],
        *,
        limit: int,
        seen_resources: set[str],
        search_query: str,
    ) -> None:
        for resource in resources:
            if len(signals) >= limit:
                break
            try:
                if not _matches_filters(resource, tags=self.tags):
                    continue
                identities = _resource_identity_keys(resource)
                if not identities or identities.intersection(seen_resources):
                    continue
                signal = _resource_to_signal(resource, adapter_name=self.name, search_query=search_query)
                seen_resources.update(identities)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse Figma Community resource object: %s", self.name, e)


def _extract_resources(data: dict, *, default_resource_type: str) -> list[dict]:
    return _dedupe_resource_rows(_extract_resource_rows(data, default_resource_type=default_resource_type))


def _extract_resource_rows(value: object, *, default_resource_type: str) -> list[dict]:
    if isinstance(value, list):
        rows: list[dict] = []
        for item in value:
            rows.extend(_extract_resource_rows(item, default_resource_type=default_resource_type))
        return rows
    if not isinstance(value, dict):
        return []

    unwrapped = _unwrap_resource(value)
    if _looks_like_resource_row(unwrapped):
        return [_normalize_resource_row(unwrapped, default_resource_type=default_resource_type)]

    rows: list[dict] = []
    for key in ("resources", "results", "items", "data", "search_results"):
        rows.extend(_extract_resource_rows(value.get(key), default_resource_type=default_resource_type))
    if not rows:
        for nested in value.values():
            rows.extend(_extract_resource_rows(nested, default_resource_type=default_resource_type))
    return rows


def _unwrap_resource(value: dict) -> dict:
    for key in ("resource", "hub_file", "plugin", "file", "community_resource"):
        nested = value.get(key)
        if isinstance(nested, dict):
            merged = {**value, **nested}
            merged.pop(key, None)
            return merged
    return value


def _looks_like_resource_row(value: dict) -> bool:
    return any(key in value for key in ("id", "key", "node_id", "url", "community_url")) and any(
        key in value for key in ("name", "title")
    )


def _normalize_resource_row(value: dict, *, default_resource_type: str) -> dict:
    resource_type = _resource_type(value, default=default_resource_type)
    resource_id = _string_or_none(
        value.get("id")
        or value.get("key")
        or value.get("node_id")
        or value.get("resource_id")
        or value.get("hub_file_id")
    )
    name = _string_or_none(value.get("name") or value.get("title"))
    author = _author_name(value)
    category = _string_or_none(value.get("category") or value.get("category_name"))
    tags = _dedupe_strings(
        [
            *_string_list(value.get("tags")),
            *_string_list(value.get("tag_names")),
            *_string_list(value.get("categories")),
            category,
        ]
    )
    url = _resource_url(
        value.get("url") or value.get("community_url") or value.get("canonical_url"),
        resource_type=resource_type,
        resource_id=resource_id,
        name=name,
    )

    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "name": name,
        "description": _string_or_none(value.get("description") or value.get("tagline")),
        "url": url,
        "author": author,
        "published_at": _parse_datetime(
            value.get("published_at")
            or value.get("community_published_at")
            or value.get("created_at")
            or value.get("createdAt")
            or value.get("updated_at")
        ),
        "likes_count": _int_or_none(
            _first_present(value, "likes", "likes_count", "like_count", "liked_count")
        ),
        "duplicate_count": _int_or_none(
            _first_present(value, "duplicates", "duplicate_count", "duplicated_count", "copies")
        ),
        "category": category,
        "tags": tags,
        "raw": value,
    }


def _resource_to_signal(resource: dict, *, adapter_name: str, search_query: str) -> Signal:
    name = _string_or_none(resource.get("name"))
    url = _string_or_none(resource.get("url"))
    if name is None or url is None:
        raise ValueError("resource missing name or URL")

    resource_type = _string_or_none(resource.get("resource_type")) or "resource"
    resource_id = _string_or_none(resource.get("resource_id"))
    published_at = resource.get("published_at") if isinstance(resource.get("published_at"), datetime) else None
    likes_count = _int_or_none(resource.get("likes_count"))
    duplicate_count = _int_or_none(resource.get("duplicate_count"))
    tags = _build_tags(resource_type=resource_type, tags=_string_list(resource.get("tags")), search_query=search_query)

    metadata = {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "likes_count": likes_count,
        "duplicates_count": duplicate_count,
        "duplicate_count": duplicate_count,
        "category": _string_or_none(resource.get("category")),
        "tags": _string_list(resource.get("tags")),
        "source_url": url,
        "search_query": search_query,
        "published_at": published_at.isoformat() if published_at is not None else None,
    }

    signal = Signal(
        id=f"{adapter_name}:{_stable_resource_key(resource)}",
        source_type=SignalSourceType.MARKETPLACE,
        source_adapter=adapter_name,
        title=f"Figma {resource_type}: {name}",
        content=(_string_or_none(resource.get("description")) or name)[:500],
        url=url,
        author=_string_or_none(resource.get("author")),
        published_at=published_at,
        tags=tags,
        credibility=_credibility(likes_count=likes_count, duplicate_count=duplicate_count),
        metadata=metadata,
    )
    return signal


def _resource_identity(resource: dict) -> str | None:
    resource_id = _string_or_none(resource.get("resource_id"))
    resource_type = _string_or_none(resource.get("resource_type")) or "resource"
    if resource_id:
        return f"{resource_type}:{resource_id}".lower()
    url = _string_or_none(resource.get("url"))
    return url.lower().rstrip("/") if url else None


def _resource_identity_keys(resource: dict) -> set[str]:
    keys: set[str] = set()
    resource_id = _string_or_none(resource.get("resource_id"))
    resource_type = _string_or_none(resource.get("resource_type")) or "resource"
    if resource_id:
        keys.add(f"{resource_type}:{resource_id}".lower())
    url = _string_or_none(resource.get("url"))
    if url:
        keys.add(url.lower().rstrip("/"))
    return keys


def _stable_resource_key(resource: dict) -> str:
    identity = _resource_identity(resource) or _string_or_none(resource.get("name")) or "unknown"
    return re.sub(r"[^a-z0-9._:-]+", "-", identity.lower()).strip("-")


def _resource_type(value: dict, *, default: str) -> str:
    raw = _string_or_none(
        value.get("resource_type")
        or value.get("type")
        or value.get("model_type")
        or value.get("content_type")
    )
    if raw is None:
        return default
    normalized = raw.lower().replace("_", "-")
    if "plugin" in normalized:
        return "plugin"
    if "file" in normalized or "template" in normalized or "widget" in normalized:
        return "file"
    return raw.lower()


def _resource_url(value: object, *, resource_type: str, resource_id: str | None, name: str | None) -> str | None:
    url = _string_or_none(value)
    if url:
        return urljoin(FIGMA_COMMUNITY_BASE_URL, url)
    if resource_id is None:
        return None
    slug = _slug(name)
    return f"{FIGMA_COMMUNITY_BASE_URL}/community/{quote(resource_type, safe='')}/{quote(resource_id, safe='')}/{slug}"


def _author_name(value: dict) -> str | None:
    for key in ("author", "creator", "publisher", "user", "profile"):
        nested = value.get(key)
        if isinstance(nested, dict):
            name = _string_or_none(
                nested.get("name")
                or nested.get("handle")
                or nested.get("username")
                or nested.get("display_name")
            )
            if name:
                return name
        elif isinstance(nested, str) and nested.strip():
            return nested.strip()
    return _string_or_none(value.get("author_name") or value.get("creator_name") or value.get("publisher_name"))


def _matches_filters(resource: dict, *, tags: list[str]) -> bool:
    if not tags:
        return True
    wanted = {tag.lower() for tag in tags}
    actual = {tag.lower() for tag in _string_list(resource.get("tags"))}
    category = _string_or_none(resource.get("category"))
    if category:
        actual.add(category.lower())
    return bool(actual.intersection(wanted))


def _build_tags(*, resource_type: str, tags: list[str], search_query: str) -> list[str]:
    return _dedupe_strings(["figma", resource_type, *tags, search_query])[:10]


def _credibility(*, likes_count: int | None, duplicate_count: int | None) -> float:
    likes_score = min(math.log10((likes_count or 0) + 1) / 6, 0.45)
    duplicate_score = min(math.log10((duplicate_count or 0) + 1) / 6, 0.35)
    return min(round(0.2 + likes_score + duplicate_score, 3), 1.0)


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


def _slug(value: str | None) -> str:
    if value is None:
        return ""
    return quote(re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-"), safe="-")


def _bool_config(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace(",", "")
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []
    return _dedupe_strings(values)


def _dedupe_strings(values: list[object]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _first_present(value: dict, *keys: str) -> object:
    for key in keys:
        if key in value and value[key] is not None:
            return value[key]
    return None


def _dedupe_resource_rows(rows: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        identities = _resource_identity_keys(row)
        if not identities or identities.intersection(seen):
            continue
        seen.update(identities)
        deduped.append(row)
    return deduped
