"""JetBrains Marketplace source adapter."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterCircuitOpenError, AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

JETBRAINS_MARKETPLACE_BASE_URL = "https://plugins.jetbrains.com"
JETBRAINS_MARKETPLACE_SEARCH = f"{JETBRAINS_MARKETPLACE_BASE_URL}/api/search/plugins"
JETBRAINS_MARKETPLACE_PLUGIN = f"{JETBRAINS_MARKETPLACE_BASE_URL}/api/plugins/{{plugin_id}}"

_DEFAULT_QUERIES = ["agent", "llm", "ai", "mcp", "copilot"]


class JetBrainsMarketplaceAdapter(SourceAdapter):
    """Fetch JetBrains Marketplace plugin adoption signals."""

    @property
    def name(self) -> str:
        return "jetbrains_marketplace"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def plugin_ids(self) -> list[str]:
        configured = self._config.get("plugin_ids", self._config.get("plugins", []))
        if not isinstance(configured, (list, tuple, set)):
            return []

        seen: set[str] = set()
        identifiers: list[str] = []
        for value in configured:
            if not isinstance(value, (str, int)):
                continue
            identifier = str(value).strip().strip("/")
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            identifiers.append(identifier)
        return identifiers

    @property
    def max_items(self) -> int | None:
        return _positive_int_or_none(self._config.get("max_items"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.max_items) if self.max_items is not None else limit
        if effective_limit <= 0:
            return []

        signals: list[Signal] = []
        seen_plugins: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                if len(signals) >= effective_limit:
                    break

                data = await self._fetch_json(
                    client,
                    JETBRAINS_MARKETPLACE_SEARCH,
                    context=f"query '{query}'",
                    params={"search": query, "page": 1, "size": min(50, effective_limit)},
                )
                if data is None:
                    continue

                await self._append_plugin_signals(
                    client,
                    signals,
                    _extract_plugins(data),
                    limit=effective_limit,
                    seen_plugins=seen_plugins,
                    search_query=query,
                    fetch_details=True,
                )

            for plugin_id in self.plugin_ids:
                if len(signals) >= effective_limit:
                    break

                data = await self._fetch_plugin_detail(client, plugin_id)
                if data is None:
                    continue

                await self._append_plugin_signals(
                    client,
                    signals,
                    [data],
                    limit=effective_limit,
                    seen_plugins=seen_plugins,
                    requested_plugin_id=plugin_id,
                    fetch_details=False,
                )

        return signals[:effective_limit]

    async def _fetch_plugin_detail(
        self,
        client: httpx.AsyncClient,
        plugin_id: str,
    ) -> dict | None:
        return await self._fetch_json(
            client,
            JETBRAINS_MARKETPLACE_PLUGIN.format(plugin_id=quote(plugin_id, safe="")),
            context=f"plugin '{plugin_id}'",
            params={},
        )

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
                headers={"User-Agent": "max-jetbrains-marketplace-adapter/0.1"},
            )
            return resp.json()
        except (AdapterCircuitOpenError, AdapterFetchError) as e:
            logger.warning(
                "%s: failed to fetch JetBrains Marketplace data for %s: %s",
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

    async def _append_plugin_signals(
        self,
        client: httpx.AsyncClient,
        signals: list[Signal],
        plugins: list[dict],
        *,
        limit: int,
        seen_plugins: set[str],
        search_query: str | None = None,
        requested_plugin_id: str | None = None,
        fetch_details: bool,
    ) -> None:
        for plugin in plugins:
            if len(signals) >= limit:
                break

            try:
                identity = _plugin_identity(plugin)
                if identity is None or identity in seen_plugins:
                    continue

                detail = plugin
                plugin_id = _plugin_id(plugin)
                if fetch_details and plugin_id is not None:
                    fetched = await self._fetch_plugin_detail(client, plugin_id)
                    if isinstance(fetched, dict):
                        detail = _merge_plugin_payload(plugin, fetched)

                signal = _plugin_to_signal(
                    detail,
                    adapter_name=self.name,
                    search_query=search_query,
                    requested_plugin_id=requested_plugin_id,
                )
                seen_plugins.add(identity)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning(
                    "%s: failed to parse JetBrains Marketplace plugin object: %s",
                    self.name,
                    e,
                )


def _extract_plugins(data: dict | list) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    for key in ("plugins", "items", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _merge_plugin_payload(search_plugin: dict, detail_plugin: dict) -> dict:
    merged = dict(search_plugin)
    merged.update(detail_plugin)
    return merged


def _plugin_identity(plugin: dict) -> str | None:
    plugin_id = _plugin_id(plugin)
    if plugin_id is not None:
        return plugin_id.lower()

    xml_id = _string_or_none(plugin.get("xmlId") or plugin.get("xml_id"))
    if xml_id is not None:
        return xml_id.lower()

    name = _string_or_none(plugin.get("name"))
    vendor = _vendor_name(plugin)
    if name is None or vendor is None:
        return None
    return f"{vendor}/{name}".lower()


def _plugin_to_signal(
    plugin: dict,
    *,
    adapter_name: str,
    search_query: str | None,
    requested_plugin_id: str | None,
) -> Signal:
    plugin_id = _plugin_id(plugin)
    xml_id = _string_or_none(plugin.get("xmlId") or plugin.get("xml_id"))
    name = _string_or_none(plugin.get("name") or plugin.get("pluginName"))
    if plugin_id is None and xml_id is None:
        raise ValueError("plugin missing id or xmlId")
    if name is None:
        raise ValueError("plugin missing name")

    vendor = _vendor_name(plugin)
    version = _string_or_none(plugin.get("version") or plugin.get("latestVersion"))
    description = (
        _string_or_none(plugin.get("description"))
        or _string_or_none(plugin.get("preview"))
        or _string_or_none(plugin.get("excerpt"))
        or name
    )
    downloads = _int_or_none(
        plugin.get("downloads")
        or plugin.get("downloadCount")
        or plugin.get("download_count")
        or plugin.get("downloadsCount")
    )
    rating = _rating(plugin)
    rating_count = _int_or_none(plugin.get("ratingCount") or plugin.get("rating_count"))
    tags = _string_list(plugin.get("tags") or plugin.get("categories"))
    published_at = _parse_datetime(
        plugin.get("updateDate")
        or plugin.get("updatedDate")
        or plugin.get("date")
        or plugin.get("publishDate")
        or plugin.get("publishedAt")
    )
    source_url = _source_url(plugin, plugin_id=plugin_id, xml_id=xml_id)

    metadata = {
        "plugin_id": plugin_id,
        "xml_id": xml_id,
        "name": name,
        "vendor": vendor,
        "version": version,
        "downloads": downloads,
        "average_rating": rating,
        "rating_count": rating_count,
        "tags": tags,
        "published_at": published_at.isoformat() if published_at is not None else None,
        "source_url": source_url,
        "search_query": search_query,
        "requested_plugin_id": requested_plugin_id,
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=_title(name=name, version=version),
        content=description[:500],
        url=source_url,
        author=vendor,
        published_at=published_at,
        tags=_build_tags(tags=tags, search_query=search_query),
        credibility=_credibility(downloads=downloads, rating=rating),
        metadata=metadata,
    )


def _plugin_id(plugin: dict) -> str | None:
    value = plugin.get("id") or plugin.get("pluginId") or plugin.get("plugin_id")
    if isinstance(value, int):
        return str(value)
    return _string_or_none(value)


def _vendor_name(plugin: dict) -> str | None:
    vendor = plugin.get("vendor")
    if isinstance(vendor, str):
        return _string_or_none(vendor)
    if isinstance(vendor, dict):
        return _string_or_none(
            vendor.get("name") or vendor.get("displayName") or vendor.get("vendorName")
        )
    return _string_or_none(plugin.get("vendorName") or plugin.get("vendor_name"))


def _rating(plugin: dict) -> float | None:
    value = plugin.get("rating") or plugin.get("averageRating") or plugin.get("average_rating")
    if isinstance(value, dict):
        value = value.get("average") or value.get("rating") or value.get("value")
    return _float_or_none(value)


def _source_url(plugin: dict, *, plugin_id: str | None, xml_id: str | None) -> str:
    for key in ("url", "link", "sourceUrl", "source_url"):
        value = _string_or_none(plugin.get(key))
        if value:
            if value.startswith("/"):
                return f"{JETBRAINS_MARKETPLACE_BASE_URL}{value}"
            return value
    identifier = plugin_id or xml_id or ""
    return f"{JETBRAINS_MARKETPLACE_BASE_URL}/plugin/{quote(identifier, safe='')}"


def _title(*, name: str, version: str | None) -> str:
    return f"{name}@{version}" if version else name


def _build_tags(*, tags: list[str], search_query: str | None) -> list[str]:
    values = list(tags)
    if search_query:
        values.append(search_query)
    return _dedupe_strings(values)[:10]


def _credibility(*, downloads: int | None, rating: float | None) -> float:
    download_score = min(math.log10((downloads or 0) + 1) / 7, 0.75)
    rating_score = 0.0
    if rating is not None:
        rating_score = min(max(rating, 0.0) / 5, 1.0) * 0.15
    return min(round(0.1 + download_score + rating_score, 3), 1.0)


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

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
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        values = value
    else:
        return []
    return _dedupe_strings(item for item in values if isinstance(item, str))


def _dedupe_strings(values: object) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _positive_int_or_none(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


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
