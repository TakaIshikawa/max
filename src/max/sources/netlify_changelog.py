"""Netlify changelog source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from max.sources.base import SourceAdapter
from max.sources.twilio_changelog import _entries, _entries_from_config_or_feed, _terms, parse_datetime
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://www.netlify.com/changelog/rss/"


class NetlifyChangelogAdapter(SourceAdapter):
    config_keys = ["entries", "payload", "feed_url", "products", "keywords", "max_age_days", "timeout"]
    required_keys: list[str] = []
    description = "Converts Netlify changelog entries into deployment platform signals."

    @property
    def name(self) -> str:
        return "netlify_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        try:
            entries = await _entries_from_config_or_feed(
                {**self._config, "feed_url": self._config.get("feed_url") or DEFAULT_FEED_URL},
                self.name,
            )
            return parse_netlify_changelog(
                entries,
                feed_url=_text(self._config.get("feed_url")) or DEFAULT_FEED_URL,
                products=self._config.get("products"),
                keywords=self._config.get("keywords"),
                max_age_days=self._config.get("max_age_days"),
                limit=limit,
            )
        except Exception:
            return []


def parse_netlify_changelog(
    value: Any,
    *,
    feed_url: str = DEFAULT_FEED_URL,
    products: Any = None,
    keywords: Any = None,
    max_age_days: Any = None,
    limit: int | None = None,
) -> list[Signal]:
    product_terms = _terms(products)
    keyword_terms = _terms(keywords)
    max_age = _int(max_age_days)
    signals: list[Signal] = []
    seen_urls: set[str] = set()
    for entry in _entries(value):
        title = _text(entry.get("title") or entry.get("name"))
        url = _text(entry.get("url") or entry.get("link"))
        if not title or not url or url in seen_urls:
            continue
        content = _text(entry.get("content") or entry.get("summary") or entry.get("description")) or title
        categories = _dedupe([*_strings(entry.get("categories")), *_strings(entry.get("tags")), _text(entry.get("category"))])
        area = _text(entry.get("product_area") or entry.get("area") or entry.get("product") or entry.get("category") or (categories[0] if categories else ""))
        impact = _text(entry.get("impact") or entry.get("change_impact"))
        published_at = parse_datetime(entry.get("published_at") or entry.get("date"))
        haystack = " ".join([title, content, area, impact, " ".join(categories)]).casefold()
        category_terms = [category.casefold() for category in categories]
        if product_terms and not any(term in haystack or term in category_terms for term in product_terms):
            continue
        if keyword_terms and not any(term in haystack for term in keyword_terms):
            continue
        if max_age is not None and published_at is not None and _now() - published_at > max_age:
            continue
        seen_urls.add(url)
        signals.append(
            Signal(
                id=f"netlify_changelog:{hashlib.sha1(url.encode()).hexdigest()[:12]}",
                source_type=SignalSourceType.ROADMAP,
                source_adapter="netlify_changelog",
                title=title,
                content=content[:1000],
                url=url,
                published_at=published_at,
                tags=_dedupe(["netlify", "deployment", area, impact, *categories, *_strings(entry.get("tags"))]),
                metadata={
                    "feed_url": feed_url,
                    "categories": [category.casefold() for category in categories],
                    "product_area": area,
                    "impact": impact,
                    "category": _text(entry.get("category")),
                },
            )
        )
        if limit is not None and len(signals) >= max(0, limit):
            break
    signals.sort(key=lambda signal: (signal.published_at or datetime.min.replace(tzinfo=timezone.utc), signal.id), reverse=True)
    return signals


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    return [_text(item) for item in value if _text(item)] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _text(value)
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _int(value: Any):
    from datetime import timedelta

    try:
        days = max(0, int(float(value))) if value is not None else None
    except (TypeError, ValueError):
        return None
    return timedelta(days=days) if days is not None else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
