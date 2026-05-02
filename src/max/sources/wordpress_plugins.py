"""WordPress.org plugin directory source adapter."""

from __future__ import annotations

import html
import logging
import math
import re
from datetime import datetime, timezone

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

WORDPRESS_PLUGINS_API_URL = "https://api.wordpress.org/plugins/info/1.2/"
WORDPRESS_PLUGIN_URL = "https://wordpress.org/plugins/{slug}/"

DEFAULT_QUERIES = [
    "booking",
    "woocommerce",
    "membership",
    "security",
    "forms",
    "analytics",
]


class WordPressPluginsAdapter(SourceAdapter):
    """Fetch WordPress.org plugin directory search results."""

    @property
    def name(self) -> str:
        return "wordpress_plugins"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", DEFAULT_QUERIES)

    @property
    def api_url(self) -> str:
        return str(self._config.get("api_url", WORDPRESS_PLUGINS_API_URL))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = max(limit, 0)
        if item_limit == 0:
            return []

        signals: list[Signal] = []
        seen_slugs: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                if len(signals) >= item_limit:
                    break

                payload = await self._fetch_query(client, query, item_limit - len(signals))
                if payload is None:
                    continue

                plugins = payload.get("plugins")
                if not isinstance(plugins, list):
                    logger.warning("%s: malformed plugin results for query '%s'", self.name, query)
                    continue

                for plugin in plugins:
                    if len(signals) >= item_limit:
                        break
                    if not isinstance(plugin, dict):
                        logger.warning("%s: malformed plugin record for query '%s'", self.name, query)
                        continue

                    slug = _normalize_slug(plugin.get("slug"))
                    if not slug or slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)

                    signal = _plugin_to_signal(plugin, query=query, adapter_name=self.name)
                    if signal is None:
                        logger.warning("%s: malformed plugin record for query '%s'", self.name, query)
                        continue
                    signals.append(signal)

        return signals[:item_limit]

    async def _fetch_query(
        self,
        client: httpx.AsyncClient,
        query: str,
        remaining: int,
    ) -> dict | None:
        try:
            response = await fetch_with_retry(
                self.api_url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                params={
                    "action": "query_plugins",
                    "request[search]": query,
                    "request[page]": 1,
                    "request[per_page]": max(min(remaining, 100), 1),
                    "request[fields][description]": 0,
                    "request[fields][sections]": 0,
                    "request[fields][downloaded]": 1,
                    "request[fields][active_installs]": 1,
                    "request[fields][last_updated]": 1,
                },
                headers={"User-Agent": "max-wordpress-plugins-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch query '%s': %s", self.name, query, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for query '%s': %s", self.name, query, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse query '%s': %s", self.name, query, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed plugin results for query '%s'", self.name, query)
            return None
        return payload


def _plugin_to_signal(plugin: dict, *, query: str, adapter_name: str) -> Signal | None:
    slug = _normalize_slug(plugin.get("slug"))
    if not slug:
        return None

    name = _clean_text(plugin.get("name")) or slug
    summary = _clean_text(plugin.get("short_description")) or name
    author = _clean_text(plugin.get("author")) or None
    rating = _number_or_none(plugin.get("rating"))
    active_installs = _int_or_none(plugin.get("active_installs"))
    downloaded = _int_or_none(plugin.get("downloaded"))
    last_updated = _parse_datetime(plugin.get("last_updated"))
    plugin_tags = _normalize_tags(plugin.get("tags"))
    plugin_url = WORDPRESS_PLUGIN_URL.format(slug=slug)

    return Signal(
        id=f"wordpress_plugins:{slug}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=name,
        content=summary,
        url=plugin_url,
        author=author,
        published_at=last_updated,
        tags=_build_tags(slug, plugin_tags),
        credibility=_credibility(rating, active_installs),
        metadata={
            "signal_role": "market",
            "package_ecosystem": "wordpress",
            "wordpress_slug": slug,
            "plugin_name": name,
            "search_query": query,
            "rating": rating,
            "active_installs": active_installs,
            "downloaded": downloaded,
            "short_description": summary,
            "author": author,
            "tags": plugin_tags,
            "last_updated": last_updated.isoformat() if last_updated else None,
            "source_url": plugin_url,
            "plugin_url": plugin_url,
        },
    )


def _normalize_slug(value: object) -> str:
    if not isinstance(value, str):
        return ""
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug)
    return slug.strip("-._")


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_tags(value: object) -> list[str]:
    if isinstance(value, dict):
        raw_tags = value.values()
    elif isinstance(value, list | tuple | set):
        raw_tags = value
    else:
        raw_tags = []

    tags: list[str] = []
    seen: set[str] = set()
    for tag in raw_tags:
        cleaned = _clean_text(tag).lower()
        normalized = re.sub(r"[^a-z0-9._-]+", "-", cleaned).strip("-._")
        if normalized and normalized not in seen:
            seen.add(normalized)
            tags.append(normalized)
    return tags


def _number_or_none(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _int_or_none(value: object) -> int | None:
    number = _number_or_none(value)
    if number is None:
        return None
    return max(int(number), 0)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None

    if parsed is None:
        for fmt in ("%Y-%m-%d %I:%M%p %Z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_tags(slug: str, plugin_tags: list[str]) -> list[str]:
    tags = ["wordpress", "wordpress-plugin", "plugin-directory", slug]
    for tag in plugin_tags:
        if tag not in tags:
            tags.append(tag)
    return tags[:10]


def _credibility(rating: float | None, active_installs: int | None) -> float:
    rating_score = (rating or 0) / 100
    install_score = min(math.log10(max(active_installs or 0, 1)) / 6, 1.0)
    return round(max(0.2, min((rating_score * 0.6) + (install_score * 0.4), 1.0)), 3)
