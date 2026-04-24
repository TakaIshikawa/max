"""Open VSX Registry source adapter — VS Code-compatible extension signals."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

OPEN_VSX_BASE_URL = "https://open-vsx.org"
OPEN_VSX_SEARCH = f"{OPEN_VSX_BASE_URL}/api/-/search"
OPEN_VSX_EXTENSION = f"{OPEN_VSX_BASE_URL}/api/{{namespace}}/{{name}}"

_DEFAULT_QUERIES = ["agent", "llm", "ai", "mcp", "copilot"]


class OpenVsxAdapter(SourceAdapter):
    """Fetch VS Code-compatible extension signals from the Open VSX Registry."""

    @property
    def name(self) -> str:
        return "open_vsx"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def extensions(self) -> list[str]:
        configured = self._config.get("extensions", self._config.get("extension_identifiers", []))
        values = list(configured or [])
        seen: set[str] = set()
        identifiers: list[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            identifier = value.strip().strip("/")
            if not identifier or "/" not in identifier or identifier in seen:
                continue
            seen.add(identifier)
            identifiers.append(identifier)
        return identifiers

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_extensions: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    OPEN_VSX_SEARCH,
                    context=f"query '{query}'",
                    params={"query": query, "size": min(50, max(1, limit - len(signals)))},
                )
                if data is None:
                    continue

                self._append_extension_signals(
                    signals,
                    _extract_search_extensions(data),
                    limit=limit,
                    seen_extensions=seen_extensions,
                    search_query=query,
                )

            for identifier in self.extensions:
                if len(signals) >= limit:
                    break

                namespace, name = identifier.split("/", 1)
                data = await self._fetch_json(
                    client,
                    OPEN_VSX_EXTENSION.format(
                        namespace=quote(namespace, safe=""),
                        name=quote(name, safe=""),
                    ),
                    context=f"extension '{identifier}'",
                    params={},
                )
                if data is None:
                    continue

                self._append_extension_signals(
                    signals,
                    [data],
                    limit=limit,
                    seen_extensions=seen_extensions,
                    extension_identifier=identifier,
                )

        return signals[:limit]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | list | None:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-open-vsx-adapter/0.1"},
            )
            return resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Open VSX data for %s: %s", self.name, context, e)
        except ValueError as e:
            logger.warning("%s: failed to parse JSON response for %s: %s", self.name, context, e)
        return None

    def _append_extension_signals(
        self,
        signals: list[Signal],
        extensions: list[dict],
        *,
        limit: int,
        seen_extensions: set[str],
        search_query: str | None = None,
        extension_identifier: str | None = None,
    ) -> None:
        for extension in extensions:
            if len(signals) >= limit:
                break

            try:
                normalized = _extension_payload(extension)
                identity = _extension_identity(normalized)
                if identity is None or identity in seen_extensions:
                    continue

                signal = _extension_to_signal(
                    normalized,
                    adapter_name=self.name,
                    search_query=search_query,
                    extension_identifier=extension_identifier,
                )
                seen_extensions.add(identity)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse Open VSX extension object: %s", self.name, e)


def _extract_search_extensions(data: dict | list) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    for key in ("extensions", "items", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extension_payload(value: dict) -> dict:
    nested = value.get("extension")
    if isinstance(nested, dict):
        return nested
    return value


def _extension_identity(extension: dict) -> str | None:
    namespace = _string_or_none(extension.get("namespace"))
    name = _string_or_none(extension.get("name"))
    if namespace is None or name is None:
        return None
    return f"{namespace}/{name}".lower()


def _extension_to_signal(
    extension: dict,
    *,
    adapter_name: str,
    search_query: str | None,
    extension_identifier: str | None,
) -> Signal:
    namespace = _string_or_none(extension.get("namespace"))
    name = _string_or_none(extension.get("name"))
    if namespace is None or name is None:
        raise ValueError("extension missing namespace or name")

    version = _string_or_none(extension.get("version"))
    display_name = _string_or_none(extension.get("displayName") or extension.get("display_name"))
    description = _string_or_none(extension.get("description")) or display_name or name
    download_count = _int_or_none(
        extension.get("downloadCount")
        or extension.get("download_count")
        or extension.get("downloads")
    )
    average_rating = _float_or_none(
        extension.get("averageRating")
        or extension.get("average_rating")
        or extension.get("rating")
    )
    categories = _string_list(extension.get("categories") or extension.get("category"))
    extension_tags = _string_list(extension.get("tags"))
    repository = _repository_url(extension.get("repository"))
    license_value = _string_or_none(extension.get("license"))
    published_at = _parse_datetime(
        extension.get("timestamp")
        or extension.get("publishedAt")
        or extension.get("published_at")
        or extension.get("lastUpdated")
        or extension.get("last_updated")
    )
    source_url = _source_url(extension, namespace=namespace, name=name)

    metadata = {
        "namespace": namespace,
        "name": name,
        "version": version,
        "download_count": download_count,
        "average_rating": average_rating,
        "categories": categories,
        "tags": extension_tags,
        "repository": repository,
        "license": license_value,
        "published_at": published_at.isoformat() if published_at is not None else None,
        "source_url": source_url,
        "search_query": search_query,
        "extension_identifier": extension_identifier,
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=_title(namespace=namespace, name=name, display_name=display_name, version=version),
        content=description[:500],
        url=source_url,
        author=namespace,
        published_at=published_at,
        tags=_build_tags(categories=categories, tags=extension_tags, search_query=search_query),
        credibility=_credibility(download_count=download_count, average_rating=average_rating),
        metadata=metadata,
    )


def _title(*, namespace: str, name: str, display_name: str | None, version: str | None) -> str:
    base = display_name or f"{namespace}/{name}"
    return f"{base}@{version}" if version else base


def _source_url(extension: dict, *, namespace: str, name: str) -> str:
    for key in ("url", "sourceUrl", "source_url"):
        value = _string_or_none(extension.get(key))
        if value:
            return value
    return f"{OPEN_VSX_BASE_URL}/extension/{quote(namespace, safe='')}/{quote(name, safe='')}"


def _repository_url(value: object) -> str | None:
    if isinstance(value, str):
        return _string_or_none(value)
    if isinstance(value, dict):
        return _string_or_none(value.get("url") or value.get("repositoryUrl") or value.get("homepage"))
    return None


def _build_tags(
    *,
    categories: list[str],
    tags: list[str],
    search_query: str | None,
) -> list[str]:
    values = [*categories, *tags]
    if search_query:
        values.append(search_query)

    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped[:10]


def _credibility(*, download_count: int | None, average_rating: float | None) -> float:
    download_score = min(math.log10((download_count or 0) + 1) / 7, 0.75)
    rating_score = 0.0
    if average_rating is not None:
        rating_score = min(max(average_rating, 0.0) / 5, 1.0) * 0.15
    return min(round(0.1 + download_score + rating_score, 3), 1.0)


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


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []

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


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
