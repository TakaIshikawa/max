"""Crates.io source adapter — Rust ecosystem package trends."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

CRATES_SEARCH = "https://crates.io/api/v1/crates"
CRATES_CATEGORY = "https://crates.io/api/v1/categories/{category}/crates"

_DEFAULT_QUERIES = ["ai", "llm", "agent", "async", "wasm"]
_DEFAULT_CATEGORIES = ["development-tools", "command-line-utilities"]


class CratesIoAdapter(SourceAdapter):
    """Fetch Rust package trend signals from the Crates.io API."""

    @property
    def name(self) -> str:
        return "crates_io"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_crates: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    CRATES_SEARCH,
                    context=f"query '{query}'",
                    params={"q": query, "per_page": min(10, limit - len(signals))},
                )
                if data is None:
                    continue

                self._append_crate_signals(
                    signals,
                    data.get("crates", []),
                    limit=limit,
                    seen_crates=seen_crates,
                    search_query=query,
                )

            for category in self.categories:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    CRATES_CATEGORY.format(category=category),
                    context=f"category '{category}'",
                    params={"per_page": min(10, limit - len(signals))},
                )
                if data is None:
                    continue

                self._append_crate_signals(
                    signals,
                    data.get("crates", []),
                    limit=limit,
                    seen_crates=seen_crates,
                    category=category,
                )

        return signals[:limit]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | None:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-crates-io-adapter/0.1"},
            )
            return resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch crates for %s: %s", self.name, context, e)
        except ValueError as e:
            logger.warning("%s: failed to parse JSON response for %s: %s", self.name, context, e)
        return None

    def _append_crate_signals(
        self,
        signals: list[Signal],
        crates: list[dict],
        *,
        limit: int,
        seen_crates: set[str],
        search_query: str | None = None,
        category: str | None = None,
    ) -> None:
        for crate in crates:
            if len(signals) >= limit:
                break

            try:
                crate_name = str(crate.get("name") or crate.get("id") or "").strip()
                if not crate_name or crate_name in seen_crates:
                    continue

                seen_crates.add(crate_name)
                signals.append(
                    _crate_to_signal(
                        crate,
                        adapter_name=self.name,
                        search_query=search_query,
                        category=category,
                    )
                )
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse crate object: %s", self.name, e)


def _crate_to_signal(
    crate: dict,
    *,
    adapter_name: str,
    search_query: str | None = None,
    category: str | None = None,
) -> Signal:
    crate_name = str(crate.get("name") or crate.get("id") or "")
    version = str(crate.get("max_version") or crate.get("newest_version") or "")
    description = str(crate.get("description") or crate_name)
    downloads = _int_or_none(crate.get("downloads")) or 0
    recent_downloads = _int_or_none(crate.get("recent_downloads"))
    updated_at = _parse_datetime(crate.get("updated_at"))
    homepage = _string_or_none(crate.get("homepage"))
    repository = _string_or_none(crate.get("repository"))
    documentation = _string_or_none(crate.get("documentation"))

    metadata = {
        "crate_name": crate_name,
        "version": version,
        "downloads": downloads,
        "recent_downloads": recent_downloads,
        "repository": repository,
        "homepage": homepage,
        "documentation": documentation,
        "keywords": crate.get("keywords") or [],
        "categories": crate.get("categories") or [],
        "search_query": search_query,
        "category": category,
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{crate_name}@{version}" if version else crate_name,
        content=description[:500],
        url=f"https://crates.io/crates/{crate_name}",
        author=_string_or_none(crate.get("owners")) or _string_or_none(crate.get("owner_user")),
        published_at=updated_at,
        tags=_build_tags(crate, search_query=search_query, category=category),
        credibility=_credibility(downloads=downloads, recent_downloads=recent_downloads, updated_at=updated_at),
        metadata=metadata,
    )


def _build_tags(
    crate: dict,
    *,
    search_query: str | None = None,
    category: str | None = None,
) -> list[str]:
    tags: list[str] = []
    for value in [*(crate.get("keywords") or []), *(crate.get("categories") or [])]:
        if isinstance(value, str) and value.strip():
            tags.append(value.strip())

    if search_query:
        tags.append(search_query)
    if category:
        tags.append(category)

    seen: set[str] = set()
    deduped: list[str] = []
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(
    *,
    downloads: int,
    recent_downloads: int | None,
    updated_at: datetime | None,
) -> float:
    downloads_score = min(math.log10(downloads + 1) / 7, 0.65)
    recent_score = min(math.log10((recent_downloads or 0) + 1) / 6, 0.2)
    freshness_score = 0.0

    if updated_at is not None:
        age_days = (datetime.now(timezone.utc) - updated_at).days
        if age_days <= 30:
            freshness_score = 0.15
        elif age_days <= 180:
            freshness_score = 0.1
        elif age_days <= 365:
            freshness_score = 0.05

    return min(round(0.1 + downloads_score + recent_score + freshness_score, 3), 1.0)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
