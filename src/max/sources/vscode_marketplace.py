"""Visual Studio Code Marketplace source adapter."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterCircuitOpenError, AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

VSCODE_MARKETPLACE_BASE_URL = "https://marketplace.visualstudio.com"
VSCODE_MARKETPLACE_QUERY = (
    f"{VSCODE_MARKETPLACE_BASE_URL}/_apis/public/gallery/extensionquery"
)

_DEFAULT_QUERIES = ["agent", "llm", "ai", "mcp", "copilot"]
_TARGET_PLATFORM = "Microsoft.VisualStudio.Code"

# Public gallery extension query filter types used by the VS Code Marketplace.
_FILTER_TAG = 8
_FILTER_SEARCH_TEXT = 10
_FILTER_EXTENSION_NAME = 7

# Include metadata, statistics, version properties, and asset URLs.
_QUERY_FLAGS = 0x1 | 0x2 | 0x4 | 0x10 | 0x20 | 0x80 | 0x100 | 0x200


class VSCodeMarketplaceAdapter(SourceAdapter):
    """Fetch Visual Studio Code Marketplace extension adoption signals."""

    @property
    def name(self) -> str:
        return "vscode_marketplace"

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
            if not identifier or identifier in seen:
                continue
            if "/" not in identifier and "." not in identifier:
                continue
            seen.add(identifier)
            identifiers.append(identifier)
        return identifiers

    @property
    def max_items(self) -> int | None:
        return _positive_int_or_none(self._config.get("max_items"))

    @property
    def categories(self) -> list[str]:
        return _normalized_filter_terms(self._config.get("categories"))

    @property
    def tag_filters(self) -> list[str]:
        return _normalized_filter_terms(self._config.get("tags"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.max_items) if self.max_items is not None else limit
        if effective_limit <= 0:
            return []

        signals: list[Signal] = []
        seen_extensions: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                if len(signals) >= effective_limit:
                    break

                data = await self._fetch_json(
                    client,
                    context=f"query '{query}'",
                    body=_query_body(
                        criteria=[
                            {"filterType": _FILTER_SEARCH_TEXT, "value": query},
                            {"filterType": _FILTER_TAG, "value": _TARGET_PLATFORM},
                        ],
                        page_size=min(100, max(1, effective_limit - len(signals))),
                    ),
                )
                if data is None:
                    continue

                self._append_extension_signals(
                    signals,
                    _extract_extensions(data),
                    limit=effective_limit,
                    seen_extensions=seen_extensions,
                    search_query=query,
                )

            for identifier in self.extensions:
                if len(signals) >= effective_limit:
                    break

                data = await self._fetch_json(
                    client,
                    context=f"extension '{identifier}'",
                    body=_query_body(
                        criteria=[
                            {"filterType": _FILTER_EXTENSION_NAME, "value": identifier},
                            {"filterType": _FILTER_TAG, "value": _TARGET_PLATFORM},
                        ],
                        page_size=1,
                    ),
                )
                if data is None:
                    continue

                self._append_extension_signals(
                    signals,
                    _extract_extensions(data),
                    limit=effective_limit,
                    seen_extensions=seen_extensions,
                    extension_identifier=identifier,
                )

        return signals[:effective_limit]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        *,
        context: str,
        body: dict[str, object],
    ) -> dict | None:
        try:
            resp = await fetch_with_retry(
                VSCODE_MARKETPLACE_QUERY,
                client,
                adapter_name=self.name,
                method="POST",
                params={"api-version": "7.2-preview.1"},
                headers={
                    "Accept": "application/json;api-version=7.2-preview.1",
                    "Content-Type": "application/json",
                    "User-Agent": "max-vscode-marketplace-adapter/0.1",
                },
                json=body,
            )
            data = resp.json()
            return data if isinstance(data, dict) else None
        except (AdapterCircuitOpenError, AdapterFetchError) as e:
            logger.warning(
                "%s: failed to fetch VS Code Marketplace data for %s: %s",
                self.name,
                context,
                e,
            )
        except ValueError as e:
            logger.warning(
                "%s: failed to parse JSON response for %s: %s",
                self.name,
                context,
                e,
            )
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
                identity = _extension_identity(extension)
                if identity is None or identity in seen_extensions:
                    continue
                if not _matches_filters(
                    extension,
                    categories=self.categories,
                    tags=self.tag_filters,
                ):
                    continue

                signal = _extension_to_signal(
                    extension,
                    adapter_name=self.name,
                    search_query=search_query,
                    extension_identifier=extension_identifier,
                )
                seen_extensions.add(identity)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning(
                    "%s: failed to parse VS Code Marketplace extension object: %s",
                    self.name,
                    e,
                )


def _query_body(*, criteria: list[dict[str, object]], page_size: int) -> dict[str, object]:
    return {
        "filters": [
            {
                "criteria": criteria,
                "pageNumber": 1,
                "pageSize": page_size,
                "sortBy": 0,
                "sortOrder": 0,
            }
        ],
        "assetTypes": [],
        "flags": _QUERY_FLAGS,
    }


def _extract_extensions(data: dict) -> list[dict]:
    extensions: list[dict] = []
    results = data.get("results")
    if not isinstance(results, list):
        return extensions

    for result in results:
        if not isinstance(result, dict):
            continue
        values = result.get("extensions")
        if isinstance(values, list):
            extensions.extend(item for item in values if isinstance(item, dict))
    return extensions


def _extension_identity(extension: dict) -> str | None:
    publisher = _publisher_name(extension)
    name = _string_or_none(extension.get("extensionName"))
    if publisher is None or name is None:
        return None
    return f"{publisher}.{name}".lower()


def _extension_to_signal(
    extension: dict,
    *,
    adapter_name: str,
    search_query: str | None,
    extension_identifier: str | None,
) -> Signal:
    publisher = _publisher_name(extension)
    name = _string_or_none(extension.get("extensionName"))
    if publisher is None or name is None:
        raise ValueError("extension missing publisher or extensionName")

    version_payload = _latest_version(extension)
    version = _string_or_none(version_payload.get("version")) if version_payload else None
    display_name = _string_or_none(extension.get("displayName")) or name
    description = _string_or_none(extension.get("shortDescription")) or display_name
    categories = _string_list(extension.get("categories"))
    tags = _property_list(version_payload, "Microsoft.VisualStudio.Code.ExtensionTags")
    install_count = _statistic(extension, "install")
    download_count = _statistic(extension, "downloadCount")
    rating = _statistic(extension, "averagerating")
    rating_count = _statistic(extension, "ratingcount")
    published_at = _parse_datetime(
        version_payload.get("lastUpdated") if version_payload else extension.get("lastUpdated")
    )
    source_url = _marketplace_url(publisher=publisher, name=name)
    repository = _repository_url(version_payload)

    metadata = {
        "publisher": publisher,
        "publisher_display_name": _publisher_display_name(extension),
        "name": name,
        "version": version,
        "install_count": _int_or_none(install_count),
        "download_count": _int_or_none(download_count),
        "average_rating": rating,
        "rating_count": _int_or_none(rating_count),
        "categories": categories,
        "tags": tags,
        "repository": repository,
        "published_at": published_at.isoformat() if published_at is not None else None,
        "source_url": source_url,
        "search_query": search_query,
        "extension_identifier": extension_identifier,
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=_title(display_name=display_name, version=version),
        content=description[:500],
        url=source_url,
        author=publisher,
        published_at=published_at,
        tags=_build_tags(categories=categories, tags=tags, search_query=search_query),
        credibility=_credibility(install_count=install_count, rating=rating),
        metadata=metadata,
    )


def _latest_version(extension: dict) -> dict:
    versions = extension.get("versions")
    if isinstance(versions, list):
        for version in versions:
            if isinstance(version, dict):
                return version
    return {}


def _publisher_name(extension: dict) -> str | None:
    publisher = extension.get("publisher")
    if isinstance(publisher, dict):
        return _string_or_none(publisher.get("publisherName") or publisher.get("publisherId"))
    return _string_or_none(extension.get("publisherName"))


def _publisher_display_name(extension: dict) -> str | None:
    publisher = extension.get("publisher")
    if isinstance(publisher, dict):
        return _string_or_none(publisher.get("displayName") or publisher.get("publisherName"))
    return None


def _property_list(version: dict, key: str) -> list[str]:
    properties = version.get("properties")
    if not isinstance(properties, list):
        return []
    values: list[str] = []
    for item in properties:
        if not isinstance(item, dict) or item.get("key") != key:
            continue
        raw_value = item.get("value")
        if isinstance(raw_value, str):
            values.extend(part.strip() for part in raw_value.split(","))
    return _dedupe_strings(values)


def _repository_url(version: dict) -> str | None:
    properties = version.get("properties")
    if not isinstance(properties, list):
        return None
    for item in properties:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if key in {
            "Microsoft.VisualStudio.Services.Links.Source",
            "Microsoft.VisualStudio.Services.Links.GitHub",
            "Microsoft.VisualStudio.Services.Links.Repository",
        }:
            return _string_or_none(item.get("value"))
    return None


def _statistic(extension: dict, name: str) -> float | None:
    statistics = extension.get("statistics")
    if not isinstance(statistics, list):
        return None
    for item in statistics:
        if not isinstance(item, dict):
            continue
        if _string_or_none(item.get("statisticName")) == name:
            return _float_or_none(item.get("value"))
    return None


def _matches_filters(extension: dict, *, categories: list[str], tags: list[str]) -> bool:
    if not categories and not tags:
        return True

    version = _latest_version(extension)
    extension_categories = {item.lower() for item in _string_list(extension.get("categories"))}
    extension_tags = {
        item.lower()
        for item in _property_list(version, "Microsoft.VisualStudio.Code.ExtensionTags")
    }

    if categories and not extension_categories.intersection(categories):
        return False
    if tags and not extension_tags.intersection(tags):
        return False
    return True


def _title(*, display_name: str, version: str | None) -> str:
    return f"{display_name}@{version}" if version else display_name


def _marketplace_url(*, publisher: str, name: str) -> str:
    return (
        f"{VSCODE_MARKETPLACE_BASE_URL}/items"
        f"?itemName={quote(publisher, safe='')}.{quote(name, safe='')}"
    )


def _build_tags(
    *,
    categories: list[str],
    tags: list[str],
    search_query: str | None,
) -> list[str]:
    values = [*categories, *tags]
    if search_query:
        values.append(search_query)
    return _dedupe_strings(values)[:10]


def _credibility(*, install_count: float | None, rating: float | None) -> float:
    install_score = min(math.log10((install_count or 0) + 1) / 7, 0.75)
    rating_score = 0.0
    if rating is not None:
        rating_score = min(max(rating, 0.0) / 5, 1.0) * 0.15
    return min(round(0.1 + install_score + rating_score, 3), 1.0)


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


def _normalized_filter_terms(value: object) -> list[str]:
    return [item.lower() for item in _string_list(value)]


def _positive_int_or_none(value: object) -> int | None:
    parsed = _int_or_none(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


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
