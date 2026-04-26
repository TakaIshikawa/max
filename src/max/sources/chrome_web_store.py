"""Chrome Web Store source adapter."""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urljoin

import httpx

from max.sources.base import AdapterCircuitOpenError, AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

CHROME_WEB_STORE_BASE_URL = "https://chromewebstore.google.com"
CHROME_WEB_STORE_SEARCH_URL = f"{CHROME_WEB_STORE_BASE_URL}/search/{{query}}"
CHROME_WEB_STORE_CATEGORY_URL = f"{CHROME_WEB_STORE_BASE_URL}/category/{{category}}"

_DEFAULT_QUERIES = ["developer tools", "ai agent", "llm", "mcp"]
_INSTALL_RE = re.compile(r"([\d,.]+)\s*([kKmMbB]?)")


class ChromeWebStoreAdapter(SourceAdapter):
    """Fetch browser extension marketplace and workflow signals."""

    @property
    def name(self) -> str:
        return "chrome_web_store"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def categories(self) -> list[str]:
        return _string_list(self._config.get("categories"))

    @property
    def min_rating(self) -> float | None:
        return _float_or_none(self._config.get("min_rating"))

    @property
    def min_users(self) -> int | None:
        return _int_or_none(self._config.get("min_users"))

    @property
    def max_items(self) -> int | None:
        value = _int_or_none(self._config.get("max_items"))
        return value if value is not None and value > 0 else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.max_items) if self.max_items is not None else limit
        if effective_limit <= 0:
            return []

        signals: list[Signal] = []
        seen_extensions: set[str] = set()

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for query in self.queries:
                if len(signals) >= effective_limit:
                    break
                text = await self._fetch_text(
                    client,
                    CHROME_WEB_STORE_SEARCH_URL.format(query=quote(query, safe="")),
                    context=f"query '{query}'",
                    params={"hl": "en"},
                )
                if text is None:
                    continue
                self._append_extension_signals(
                    signals,
                    parse_chrome_web_store_response(text),
                    limit=effective_limit,
                    seen_extensions=seen_extensions,
                    search_query=query,
                )

            for category in self.categories:
                if len(signals) >= effective_limit:
                    break
                text = await self._fetch_text(
                    client,
                    CHROME_WEB_STORE_CATEGORY_URL.format(category=quote(category, safe="")),
                    context=f"category '{category}'",
                    params={"hl": "en"},
                )
                if text is None:
                    continue
                self._append_extension_signals(
                    signals,
                    parse_chrome_web_store_response(text),
                    limit=effective_limit,
                    seen_extensions=seen_extensions,
                    category_query=category,
                )

        return signals[:effective_limit]

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
                headers={"User-Agent": "max-chrome-web-store-adapter/0.1"},
            )
            return resp.text
        except (AdapterCircuitOpenError, AdapterFetchError) as e:
            logger.warning("%s: failed to fetch Chrome Web Store data for %s: %s", self.name, context, e)
        except httpx.RequestError as e:
            logger.warning("%s: request failed for Chrome Web Store %s: %s", self.name, context, e)
        return None

    def _append_extension_signals(
        self,
        signals: list[Signal],
        extensions: list[dict],
        *,
        limit: int,
        seen_extensions: set[str],
        search_query: str | None = None,
        category_query: str | None = None,
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
                    min_rating=self.min_rating,
                    min_users=self.min_users,
                ):
                    continue
                signal = _extension_to_signal(
                    extension,
                    adapter_name=self.name,
                    search_query=search_query,
                    category_query=category_query,
                )
                seen_extensions.add(identity)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse Chrome Web Store extension object: %s", self.name, e)


def parse_chrome_web_store_response(text: str) -> list[dict]:
    """Parse Chrome Web Store JSON or fixture HTML into normalized extension rows."""
    stripped = text.strip()
    if not stripped:
        return []

    if stripped[0] in "[{":
        try:
            return _extract_extension_rows(json.loads(stripped))
        except json.JSONDecodeError:
            pass

    parser = _ChromeWebStoreHTMLParser()
    parser.feed(text)
    rows = parser.rows()
    for script in parser.json_scripts:
        rows.extend(_extract_extension_rows(script))
    return _dedupe_extension_rows(rows)


def _extract_extension_rows(value: object) -> list[dict]:
    if isinstance(value, str):
        try:
            return _extract_extension_rows(json.loads(value))
        except json.JSONDecodeError:
            return []
    if isinstance(value, list):
        rows: list[dict] = []
        for item in value:
            rows.extend(_extract_extension_rows(item))
        return rows
    if not isinstance(value, dict):
        return []

    if _looks_like_extension_row(value):
        return [_normalize_extension_row(value)]

    rows = []
    for key in ("extensions", "items", "results", "data", "extensionsList"):
        rows.extend(_extract_extension_rows(value.get(key)))
    if not rows:
        for nested in value.values():
            rows.extend(_extract_extension_rows(nested))
    return _dedupe_extension_rows(rows)


def _looks_like_extension_row(value: dict) -> bool:
    return any(key in value for key in ("extension_id", "extensionId", "id", "item_id")) and any(
        key in value for key in ("name", "title", "displayName")
    )


def _normalize_extension_row(value: dict) -> dict:
    extension_id = _string_or_none(
        value.get("extension_id")
        or value.get("extensionId")
        or value.get("item_id")
        or value.get("id")
    )
    url = _extension_url(value.get("url") or value.get("extension_url"), extension_id)
    rating = _float_or_none(
        value.get("rating")
        or value.get("average_rating")
        or value.get("averageRating")
        or _nested_get(value, "aggregateRating", "ratingValue")
    )
    users = _int_or_none(
        value.get("users")
        or value.get("user_count")
        or value.get("userCount")
        or value.get("install_count")
        or value.get("installs")
        or value.get("installCount")
    )
    if users is None:
        users = _parse_install_count(
            _string_or_none(value.get("users_text") or value.get("userText") or value.get("installs_text"))
        )

    return {
        "extension_id": extension_id,
        "name": _string_or_none(value.get("name") or value.get("title") or value.get("displayName")),
        "description": _string_or_none(value.get("description") or value.get("summary")),
        "publisher": _string_or_none(value.get("publisher") or value.get("author") or value.get("developer")),
        "category": _string_or_none(value.get("category")),
        "categories": _string_list(value.get("categories")),
        "rating": rating,
        "rating_count": _int_or_none(
            value.get("rating_count")
            or value.get("ratingCount")
            or _nested_get(value, "aggregateRating", "ratingCount")
        ),
        "user_count": users,
        "extension_url": url,
        "published_at": _parse_datetime(
            value.get("published_at") or value.get("publishedAt") or value.get("datePublished")
        ),
    }


class _ChromeWebStoreHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._cards: list[dict[str, str]] = []
        self._current_card: dict[str, str] | None = None
        self._current_text_key: str | None = None
        self._script_type: str | None = None
        self._script_chunks: list[str] = []
        self.json_scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "script":
            self._script_type = attr.get("type", "")
            self._script_chunks = []
            return
        if _has_extension_attrs(attr):
            self._current_card = dict(attr)
        if self._current_card is not None:
            text_key = attr.get("data-field") or attr.get("itemprop")
            if text_key in {"name", "description", "author", "category", "ratingValue", "ratingCount"}:
                self._current_text_key = text_key

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            script = "".join(self._script_chunks).strip()
            if script and self._script_type == "application/ld+json":
                self.json_scripts.append(script)
            self._script_type = None
            self._script_chunks = []
            return
        if self._current_card is not None and tag in {"a", "article", "div", "li"}:
            if _has_extension_attrs(self._current_card):
                self._cards.append(self._current_card)
            self._current_card = None
            self._current_text_key = None

    def handle_data(self, data: str) -> None:
        if self._script_type is not None:
            self._script_chunks.append(data)
            return
        if self._current_card is not None and self._current_text_key is not None:
            existing = self._current_card.get(self._current_text_key, "")
            self._current_card[self._current_text_key] = f"{existing} {data}".strip()

    def rows(self) -> list[dict]:
        rows = []
        for card in self._cards:
            rows.append(
                _normalize_extension_row(
                    {
                        "extension_id": card.get("data-extension-id") or card.get("data-id"),
                        "name": card.get("data-name") or card.get("name"),
                        "description": card.get("data-description") or card.get("description"),
                        "publisher": card.get("data-publisher") or card.get("author"),
                        "category": card.get("data-category") or card.get("category"),
                        "rating": card.get("data-rating") or card.get("ratingValue"),
                        "rating_count": card.get("data-rating-count") or card.get("ratingCount"),
                        "users": card.get("data-users") or card.get("data-user-count"),
                        "url": card.get("href") or card.get("data-url"),
                    }
                )
            )
        return rows


def _has_extension_attrs(attrs: dict[str, str]) -> bool:
    return bool(
        attrs.get("data-extension-id")
        or attrs.get("data-id")
        or (attrs.get("href", "").startswith("/detail/") and attrs.get("data-name"))
    )


def _extension_identity(extension: dict) -> str | None:
    extension_id = _string_or_none(extension.get("extension_id"))
    if extension_id:
        return extension_id.lower()
    url = _string_or_none(extension.get("extension_url"))
    return url.lower() if url else None


def _extension_to_signal(
    extension: dict,
    *,
    adapter_name: str,
    search_query: str | None,
    category_query: str | None,
) -> Signal:
    name = _string_or_none(extension.get("name"))
    if name is None:
        raise ValueError("extension missing name")

    category = _string_or_none(extension.get("category"))
    categories = _string_list(extension.get("categories"))
    if category:
        categories = _dedupe_strings([category, *categories])
    user_count = _int_or_none(extension.get("user_count"))
    rating = _float_or_none(extension.get("rating"))
    extension_url = _string_or_none(extension.get("extension_url"))
    if extension_url is None:
        raise ValueError("extension missing URL")
    published_at = extension.get("published_at") if isinstance(extension.get("published_at"), datetime) else None

    metadata = {
        "extension_id": _string_or_none(extension.get("extension_id")),
        "publisher": _string_or_none(extension.get("publisher")),
        "install_count": user_count,
        "user_count": user_count,
        "rating": rating,
        "average_rating": rating,
        "rating_count": _int_or_none(extension.get("rating_count")),
        "category": category,
        "categories": categories,
        "extension_url": extension_url,
        "source_url": extension_url,
        "search_query": search_query,
        "category_query": category_query,
        "published_at": published_at.isoformat() if published_at is not None else None,
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=name,
        content=(_string_or_none(extension.get("description")) or name)[:500],
        url=extension_url,
        author=_string_or_none(extension.get("publisher")),
        published_at=published_at,
        tags=_build_tags(categories=categories, search_query=search_query, category_query=category_query),
        credibility=_credibility(user_count=user_count, rating=rating),
        metadata=metadata,
    )


def _matches_filters(
    extension: dict,
    *,
    categories: list[str],
    min_rating: float | None,
    min_users: int | None,
) -> bool:
    if categories:
        wanted = {item.lower() for item in categories}
        actual = {
            item.lower()
            for item in [*_string_list(extension.get("categories")), _string_or_none(extension.get("category"))]
            if item
        }
        if not actual.intersection(wanted):
            return False
    rating = _float_or_none(extension.get("rating"))
    if min_rating is not None and (rating is None or rating < min_rating):
        return False
    users = _int_or_none(extension.get("user_count"))
    if min_users is not None and (users is None or users < min_users):
        return False
    return True


def _extension_url(value: object, extension_id: str | None) -> str | None:
    url = _string_or_none(value)
    if url:
        return urljoin(CHROME_WEB_STORE_BASE_URL, url)
    if extension_id:
        return f"{CHROME_WEB_STORE_BASE_URL}/detail/{quote(extension_id, safe='')}"
    return None


def _build_tags(
    *,
    categories: list[str],
    search_query: str | None,
    category_query: str | None,
) -> list[str]:
    values = [*categories]
    if search_query:
        values.append(search_query)
    if category_query:
        values.append(category_query)
    return _dedupe_strings(values)[:10]


def _credibility(*, user_count: int | None, rating: float | None) -> float:
    install_score = min(math.log10((user_count or 0) + 1) / 7, 0.75)
    rating_score = 0.0
    if rating is not None:
        rating_score = min(max(rating, 0.0) / 5, 1.0) * 0.15
    return min(round(0.1 + install_score + rating_score, 3), 1.0)


def _parse_install_count(value: str | None) -> int | None:
    if value is None:
        return None
    match = _INSTALL_RE.search(value.replace("+", ""))
    if match is None:
        return None
    number = float(match.group(1).replace(",", ""))
    suffix = match.group(2).lower()
    multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[suffix]
    return int(number * multiplier)


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


def _nested_get(value: dict, *keys: str) -> object:
    current: object = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _dedupe_extension_rows(rows: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        identity = _extension_identity(row)
        if identity is None or identity in seen:
            continue
        seen.add(identity)
        deduped.append(row)
    return deduped


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        values: list[object] = [value]
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


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            parsed = _parse_install_count(value)
            if parsed is not None:
                return parsed
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
