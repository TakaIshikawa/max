"""RubyGems source adapter — Ruby ecosystem package metadata and activity."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

RUBYGEMS_SEARCH = "https://rubygems.org/api/v1/search.json"
RUBYGEMS_DETAILS = "https://rubygems.org/api/v1/gems/{gem_name}.json"
RUBYGEMS_PACKAGE_PAGE = "https://rubygems.org/gems/{gem_name}"

_DEFAULT_QUERIES = ["rails", "ai", "llm", "agent", "devtools"]


class RubyGemsAdapter(SourceAdapter):
    """Fetch RubyGems package popularity, release, and description signals."""

    @property
    def name(self) -> str:
        return "rubygems"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def max_pages(self) -> int:
        return max(int(self._config.get("max_pages", 1)), 1)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_gems: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                if len(signals) >= limit:
                    break

                page = 1
                while len(signals) < limit and page <= self.max_pages:
                    search_data = await self._fetch_search_page(client, query=query, page=page)
                    if not search_data:
                        break

                    added_from_page = 0
                    for search_gem in search_data:
                        if len(signals) >= limit:
                            break
                        if not isinstance(search_gem, dict):
                            continue

                        gem_name = _string_or_none(search_gem.get("name"))
                        if gem_name is None:
                            continue

                        normalized_name = gem_name.lower()
                        if normalized_name in seen_gems:
                            continue

                        seen_gems.add(normalized_name)
                        details = await self._fetch_details(client, gem_name)
                        gem = {**search_gem, **(details or {})}
                        signal = _gem_to_signal(gem, adapter_name=self.name, search_query=query)
                        if signal is None:
                            continue

                        signals.append(signal)
                        added_from_page += 1

                    if len(signals) >= limit or added_from_page == 0:
                        break
                    page += 1

        return signals[:limit]

    async def _fetch_search_page(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        page: int,
    ) -> list[dict] | None:
        try:
            resp = await fetch_with_retry(
                RUBYGEMS_SEARCH,
                client,
                adapter_name=self.name,
                params={"query": query, "page": page},
                headers={"User-Agent": "max-rubygems-adapter/0.1"},
            )
            data = resp.json()
            return data if isinstance(data, list) else None
        except AdapterFetchError as e:
            logger.warning(
                "%s: failed to fetch RubyGems search results for query '%s' page %d: %s",
                self.name,
                query,
                page,
                e,
            )
        except ValueError as e:
            logger.warning(
                "%s: failed to parse RubyGems search response for query '%s' page %d: %s",
                self.name,
                query,
                page,
                e,
            )
        return None

    async def _fetch_details(self, client: httpx.AsyncClient, gem_name: str) -> dict | None:
        encoded_name = quote(gem_name, safe="")
        try:
            resp = await fetch_with_retry(
                RUBYGEMS_DETAILS.format(gem_name=encoded_name),
                client,
                adapter_name=self.name,
                headers={"User-Agent": "max-rubygems-adapter/0.1"},
            )
            data = resp.json()
            return data if isinstance(data, dict) else None
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch RubyGems details for '%s': %s", self.name, gem_name, e)
        except ValueError as e:
            logger.warning("%s: failed to parse RubyGems details for '%s': %s", self.name, gem_name, e)
        return None


def _gem_to_signal(
    gem: dict,
    *,
    adapter_name: str,
    search_query: str,
) -> Signal | None:
    gem_name = _string_or_none(gem.get("name"))
    if gem_name is None:
        return None

    version = _string_or_none(gem.get("version")) or ""
    version_created_at = _parse_datetime(gem.get("version_created_at"))
    downloads = _int_or_none(gem.get("downloads")) or 0
    version_downloads = _int_or_none(gem.get("version_downloads"))
    info = _string_or_none(gem.get("info")) or gem_name
    project_uri = _string_or_none(gem.get("project_uri")) or RUBYGEMS_PACKAGE_PAGE.format(
        gem_name=gem_name
    )
    source_code_uri = _string_or_none(gem.get("source_code_uri"))
    homepage_uri = _string_or_none(gem.get("homepage_uri"))
    documentation_uri = _string_or_none(gem.get("documentation_uri"))
    bug_tracker_uri = _string_or_none(gem.get("bug_tracker_uri"))
    changelog_uri = _string_or_none(gem.get("changelog_uri"))
    licenses = _string_list(gem.get("licenses"))
    tags = _build_tags(gem, search_query=search_query)

    metadata = {
        "package_ecosystem": "rubygems",
        "gem_name": gem_name,
        "package_name": gem_name,
        "version": version,
        "downloads": downloads,
        "download_count": downloads,
        "version_downloads": version_downloads,
        "version_created_at": version_created_at.isoformat() if version_created_at else None,
        "project_uri": project_uri,
        "gem_uri": _string_or_none(gem.get("gem_uri")),
        "homepage_uri": homepage_uri,
        "source_code_uri": source_code_uri,
        "documentation_uri": documentation_uri,
        "bug_tracker_uri": bug_tracker_uri,
        "changelog_uri": changelog_uri,
        "licenses": licenses,
        "search_query": search_query,
        "signal_kind": "package_metadata",
        "signal_role": "solution",
    }

    return Signal(
        id=_signal_id(gem_name, version),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{gem_name}@{version}" if version else gem_name,
        content=info[:500],
        url=project_uri,
        author=_string_or_none(gem.get("authors")),
        published_at=version_created_at,
        tags=tags,
        credibility=_credibility(
            downloads=downloads,
            version_downloads=version_downloads,
            published_at=version_created_at,
        ),
        metadata=metadata,
    )


def _signal_id(gem_name: str, version: str) -> str:
    normalized_name = gem_name.strip().lower()
    normalized_version = version.strip().lower() or "unknown"
    return f"rubygems:{normalized_name}:{normalized_version}"


def _build_tags(gem: dict, *, search_query: str) -> list[str]:
    tags: list[str] = [search_query, "ruby", "rubygems"]
    tags.extend(_string_list(gem.get("licenses")))

    if _int_or_none(gem.get("downloads")):
        tags.append("package-popularity")
    if _parse_datetime(gem.get("version_created_at")) is not None:
        tags.append("release-activity")
    if _string_or_none(gem.get("source_code_uri")):
        tags.append("open-source")

    seen: set[str] = set()
    deduped: list[str] = []
    for tag in tags:
        normalized = tag.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _credibility(
    *,
    downloads: int,
    version_downloads: int | None,
    published_at: datetime | None,
) -> float:
    downloads_score = min(math.log10(downloads + 1) / 8, 0.6)
    version_score = min(math.log10((version_downloads or 0) + 1) / 7, 0.15)
    freshness_score = 0.0

    if published_at is not None:
        age_days = (datetime.now(timezone.utc) - published_at).days
        if age_days <= 30:
            freshness_score = 0.15
        elif age_days <= 180:
            freshness_score = 0.1
        elif age_days <= 365:
            freshness_score = 0.05

    return min(round(0.1 + downloads_score + version_score + freshness_score, 3), 1.0)


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


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.replace(",", " ").split() if part.strip()]
    return []
