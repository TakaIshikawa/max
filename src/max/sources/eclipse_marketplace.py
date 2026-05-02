"""Eclipse Marketplace source adapter."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote
from xml.etree import ElementTree

import httpx

from max.sources.base import AdapterCircuitOpenError, AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

ECLIPSE_MARKETPLACE_BASE_URL = "https://marketplace.eclipse.org"
ECLIPSE_MARKETPLACE_SEARCH = f"{ECLIPSE_MARKETPLACE_BASE_URL}/api/p/search/apachesolr_search/{{query}}"
ECLIPSE_MARKETPLACE_SECTION = f"{ECLIPSE_MARKETPLACE_BASE_URL}/{{section}}/api/p"
ECLIPSE_MARKETPLACE_TAXONOMY = f"{ECLIPSE_MARKETPLACE_BASE_URL}/taxonomy/term/{{term}}/api/p"

_DEFAULT_QUERIES = ["ai", "agent", "llm", "mcp", "developer tools"]
_DEFAULT_SECTIONS = ["recent"]
_SUPPORTED_SECTIONS = {"recent", "favorites", "featured"}


class EclipseMarketplaceAdapter(SourceAdapter):
    """Fetch Eclipse Marketplace plugin adoption and activity signals."""

    @property
    def name(self) -> str:
        return "eclipse_marketplace"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def sections(self) -> list[str]:
        configured_value = self._config.get("sections")
        values = list(_DEFAULT_SECTIONS) if configured_value is None else _string_list(configured_value)
        return [value for value in values if value in _SUPPORTED_SECTIONS]

    @property
    def categories(self) -> list[str]:
        return _string_list(self._config.get("categories") or self._config.get("taxonomy_terms"))

    @property
    def max_pages(self) -> int:
        return _positive_int(self._config.get("max_pages"), 1)

    @property
    def max_items(self) -> int | None:
        value = _int_or_none(self._config.get("max_items") or self._config.get("max_results"))
        return value if value is not None and value > 0 else None

    @property
    def timeout(self) -> float:
        value = self._config.get("timeout", 30)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 30.0
        return parsed if parsed > 0 else 30.0

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.max_items) if self.max_items is not None else limit
        if effective_limit <= 0:
            return []

        signals: list[Signal] = []
        seen_plugins: set[str] = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for query in self.queries:
                if len(signals) >= effective_limit:
                    break
                await self._fetch_listing_pages(
                    client,
                    ECLIPSE_MARKETPLACE_SEARCH.format(query=quote(query, safe="")),
                    context=f"query '{query}'",
                    signals=signals,
                    seen_plugins=seen_plugins,
                    limit=effective_limit,
                    search_query=query,
                )

            for section in self.sections:
                if len(signals) >= effective_limit:
                    break
                await self._fetch_listing_pages(
                    client,
                    ECLIPSE_MARKETPLACE_SECTION.format(section=section),
                    context=f"section '{section}'",
                    signals=signals,
                    seen_plugins=seen_plugins,
                    limit=effective_limit,
                    section=section,
                )

            for category in self.categories:
                if len(signals) >= effective_limit:
                    break
                await self._fetch_listing_pages(
                    client,
                    ECLIPSE_MARKETPLACE_TAXONOMY.format(term=quote(category, safe=",")),
                    context=f"category '{category}'",
                    signals=signals,
                    seen_plugins=seen_plugins,
                    limit=effective_limit,
                    category=category,
                )

        return signals[:effective_limit]

    async def _fetch_listing_pages(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        signals: list[Signal],
        seen_plugins: set[str],
        limit: int,
        search_query: str | None = None,
        section: str | None = None,
        category: str | None = None,
    ) -> None:
        per_page = min(max(limit - len(signals), 1), 20)
        for page_num in range(1, self.max_pages + 1):
            if len(signals) >= limit:
                break

            text = await self._fetch_text(
                client,
                url,
                context=f"{context} page {page_num}",
                params={"page_num": page_num, "limit": per_page},
            )
            if text is None:
                continue

            plugins = parse_eclipse_marketplace_response(text)
            if not plugins:
                break
            self._append_plugin_signals(
                signals,
                plugins,
                limit=limit,
                seen_plugins=seen_plugins,
                search_query=search_query,
                section=section,
                category=category,
            )

    async def _fetch_text(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object],
    ) -> str | None:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-eclipse-marketplace-adapter/0.1"},
            )
            return resp.text
        except (AdapterCircuitOpenError, AdapterFetchError) as e:
            logger.warning("%s: failed to fetch Eclipse Marketplace data for %s: %s", self.name, context, e)
        except httpx.RequestError as e:
            logger.warning("%s: request failed for Eclipse Marketplace %s: %s", self.name, context, e)
        return None

    def _append_plugin_signals(
        self,
        signals: list[Signal],
        plugins: list[dict],
        *,
        limit: int,
        seen_plugins: set[str],
        search_query: str | None = None,
        section: str | None = None,
        category: str | None = None,
    ) -> None:
        for plugin in plugins:
            if len(signals) >= limit:
                break
            try:
                identity = _plugin_identity(plugin)
                if identity is None or identity in seen_plugins:
                    continue
                signal = _plugin_to_signal(
                    plugin,
                    adapter_name=self.name,
                    search_query=search_query,
                    section=section,
                    category=category,
                )
                seen_plugins.add(identity)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse Eclipse Marketplace plugin object: %s", self.name, e)


def parse_eclipse_marketplace_response(text: str) -> list[dict]:
    """Parse Eclipse Marketplace XML into normalized plugin rows."""
    if not text.strip():
        return []
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return []
    return [_node_to_plugin(node) for node in root.findall(".//node")]


def _node_to_plugin(node: ElementTree.Element) -> dict:
    categories = [
        {"id": category.get("id"), "name": category.get("name"), "url": category.get("url")}
        for category in node.findall("./categories/category")
    ]
    tags = [_element_text(tag) for tag in node.findall("./tags/tag")]
    return {
        "id": node.get("id") or _child_text(node, "id"),
        "name": node.get("name") or _child_text(node, "name"),
        "url": node.get("url") or _child_text(node, "url"),
        "type": _child_text(node, "type"),
        "owner": _child_text(node, "owner"),
        "summary": _first_text(node, ("summary", "teaser", "shortdescription", "description", "body")),
        "categories": [category for category in categories if category["name"] or category["id"]],
        "tags": [tag for tag in tags if tag],
        "license": _first_text(node, ("license", "licensetype")),
        "status": _first_text(node, ("status", "projectstatus")),
        "homepage": _first_text(node, ("homepageurl", "companyurl", "projecturl")),
        "install_url": _first_text(node, ("installurl", "updateurl")),
        "install_count": _int_or_none(_first_text(node, ("installstotal", "installs", "downloads"))),
        "favorites": _int_or_none(_first_text(node, ("favorited", "favorites"))),
        "rating": _float_or_none(_first_text(node, ("rating", "averagerating"))),
        "rating_count": _int_or_none(_first_text(node, ("ratingcount", "reviews"))),
        "updated_at": _parse_datetime(
            _first_text(node, ("changed", "updated", "lastupdated", "lastchanged", "created"))
            or node.get("timestamp")
        ),
    }


def _plugin_to_signal(
    plugin: dict,
    *,
    adapter_name: str,
    search_query: str | None,
    section: str | None,
    category: str | None,
) -> Signal:
    plugin_id = _string_or_none(plugin.get("id"))
    name = _string_or_none(plugin.get("name"))
    if plugin_id is None and name is None:
        raise ValueError("plugin missing id or name")
    title_name = name or plugin_id or "Eclipse Marketplace plugin"
    source_url = _source_url(plugin, plugin_id=plugin_id, name=title_name)
    categories = _category_names(plugin.get("categories"))
    tags = _string_list(plugin.get("tags"))
    install_count = _int_or_none(plugin.get("install_count"))
    favorites = _int_or_none(plugin.get("favorites"))
    rating = _float_or_none(plugin.get("rating"))
    rating_count = _int_or_none(plugin.get("rating_count"))
    updated_at = plugin.get("updated_at") if isinstance(plugin.get("updated_at"), datetime) else None
    summary = _string_or_none(plugin.get("summary")) or title_name

    metadata = {
        "signal_role": "market",
        "signal_kind": "plugin_activity",
        "evidence_type": "marketplace_listing",
        "marketplace": "eclipse_marketplace",
        "plugin_id": plugin_id,
        "name": name,
        "owner": _string_or_none(plugin.get("owner")),
        "type": _string_or_none(plugin.get("type")),
        "categories": categories,
        "tags": tags,
        "license": _string_or_none(plugin.get("license")),
        "status": _string_or_none(plugin.get("status")),
        "homepage": _string_or_none(plugin.get("homepage")),
        "install_url": _string_or_none(plugin.get("install_url")),
        "install_count": install_count,
        "favorites": favorites,
        "average_rating": rating,
        "rating_count": rating_count,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "source_url": source_url,
        "search_query": search_query,
        "section": section,
        "category": category,
    }

    return Signal(
        id=f"eclipse-marketplace:{(plugin_id or title_name).lower()}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=title_name,
        content=_content(summary, install_count=install_count, favorites=favorites, rating=rating),
        url=source_url,
        author=metadata["owner"],
        published_at=updated_at,
        tags=_build_tags(categories=categories, tags=tags, search_query=search_query, section=section),
        credibility=_credibility(install_count=install_count, favorites=favorites, rating=rating),
        metadata=metadata,
    )


def _content(
    summary: str,
    *,
    install_count: int | None,
    favorites: int | None,
    rating: float | None,
) -> str:
    parts = [summary[:500]]
    if install_count is not None:
        parts.append(f"Installs: {install_count:,}")
    if favorites is not None:
        parts.append(f"Favorites: {favorites:,}")
    if rating is not None:
        parts.append(f"Rating: {rating:g}/5")
    return " | ".join(parts)


def _plugin_identity(plugin: dict) -> str | None:
    plugin_id = _string_or_none(plugin.get("id"))
    if plugin_id:
        return plugin_id.lower()
    url = _string_or_none(plugin.get("url"))
    if url:
        return url.lower()
    name = _string_or_none(plugin.get("name"))
    return name.lower() if name else None


def _source_url(plugin: dict, *, plugin_id: str | None, name: str) -> str:
    value = _string_or_none(plugin.get("url"))
    if value:
        if value.startswith("/"):
            return f"{ECLIPSE_MARKETPLACE_BASE_URL}{value}"
        return value
    if plugin_id:
        return f"{ECLIPSE_MARKETPLACE_BASE_URL}/node/{quote(plugin_id, safe='')}"
    return f"{ECLIPSE_MARKETPLACE_BASE_URL}/search/{quote(name, safe='')}"


def _build_tags(
    *,
    categories: list[str],
    tags: list[str],
    search_query: str | None,
    section: str | None,
) -> list[str]:
    values = ["eclipse", "marketplace", "ide-plugin", *categories, *tags]
    if search_query:
        values.append(search_query)
    if section:
        values.append(section)
    return _dedupe_strings(values)[:12]


def _credibility(
    *,
    install_count: int | None,
    favorites: int | None,
    rating: float | None,
) -> float:
    install_score = min(math.log10((install_count or 0) + 1) / 7, 0.65)
    favorite_score = min(math.log10((favorites or 0) + 1) / 5, 0.15)
    rating_score = 0.0
    if rating is not None:
        rating_score = min(max(rating, 0.0) / 5, 1.0) * 0.1
    return min(round(0.1 + install_score + favorite_score + rating_score, 3), 1.0)


def _child_text(node: ElementTree.Element, tag: str) -> str | None:
    child = node.find(tag)
    return _element_text(child) if child is not None else None


def _first_text(node: ElementTree.Element, tags: tuple[str, ...]) -> str | None:
    for tag in tags:
        value = _child_text(node, tag)
        if value:
            return value
    return None


def _element_text(element: ElementTree.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    return _string_or_none(element.text)


def _category_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, dict):
            names.append(item.get("name"))
        elif isinstance(item, str):
            names.append(item)
    return _dedupe_strings(names)


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        timestamp = float(text)
    except ValueError:
        timestamp = None
    if timestamp is not None:
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        return []
    return _dedupe_strings(values)


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


def _positive_int(value: object, default: int) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None and parsed > 0 else default


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
