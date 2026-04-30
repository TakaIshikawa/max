"""Swift Package Index source adapter - Swift ecosystem package discovery."""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

SWIFT_PACKAGE_INDEX_SEARCH = "https://swiftpackageindex.com/api/search"
SWIFT_PACKAGE_INDEX_BASE = "https://swiftpackageindex.com"

_DEFAULT_QUERIES = ["ai", "llm", "agent", "server", "testing"]


class SwiftPackageIndexAdapter(SourceAdapter):
    """Fetch Swift Package Index package metadata for configured search terms."""

    @property
    def name(self) -> str:
        return "swift_package_index"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def keywords(self) -> list[str]:
        return self._configured_terms("keywords", [])

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", [])

    @property
    def max_results(self) -> int:
        return max(_int_or_none(self._config.get("max_results")) or 10, 1)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_packages: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                if len(signals) >= limit:
                    break

                per_query_limit = min(self.max_results, limit - len(signals))
                data = await self._fetch_search(client, query=query, limit=per_query_limit)
                if data is None:
                    continue

                for item in _extract_package_items(data)[:per_query_limit]:
                    if len(signals) >= limit:
                        break

                    signal = _item_to_signal(item, adapter_name=self.name, search_query=query)
                    if signal is None:
                        continue
                    package_key = signal.metadata["package_key"]
                    if package_key in seen_packages:
                        continue
                    if not _matches_filters(
                        signal,
                        keywords=self.keywords,
                        categories=self.categories,
                    ):
                        continue

                    seen_packages.add(package_key)
                    signals.append(signal)

        return signals[:limit]

    async def _fetch_search(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        limit: int,
    ) -> dict | list | None:
        try:
            resp = await fetch_with_retry(
                SWIFT_PACKAGE_INDEX_SEARCH,
                client,
                adapter_name=self.name,
                params={"query": query, "page": 1, "per_page": limit},
                headers={"User-Agent": "max-swift-package-index-adapter/0.1"},
            )
            return resp.json()
        except AdapterFetchError as e:
            logger.warning(
                "%s: failed to fetch Swift Package Index results for query '%s': %s",
                self.name,
                query,
                e,
            )
        except ValueError as e:
            logger.warning(
                "%s: failed to parse Swift Package Index results for query '%s': %s",
                self.name,
                query,
                e,
            )
        return None


def _extract_package_items(data: dict | list) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    for key in ("results", "packages", "items", "data"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def _item_to_signal(item: dict, *, adapter_name: str, search_query: str) -> Signal | None:
    repository_url = _repository_url(item)
    package_name = _package_name(item, repository_url)
    if package_name is None:
        return None

    package_url = _package_url(item, package_name, repository_url)
    description = _string_or_none(item.get("description") or item.get("summary")) or package_name
    stars = _int_or_none(
        item.get("stars")
        or item.get("star_count")
        or item.get("github_stars")
        or item.get("githubStars")
    )
    score = _float_or_none(
        item.get("score")
        or item.get("search_score")
        or item.get("rank")
        or item.get("weighted_score")
    )
    latest_version = _string_or_none(
        item.get("latest_version") or item.get("latestRelease") or item.get("version")
    )
    updated_at = _parse_datetime(
        item.get("updated_at")
        or item.get("last_activity_at")
        or item.get("released_at")
        or item.get("created_at")
    )
    tags = _build_tags(item, search_query=search_query)
    package_key = (repository_url or package_name).strip().lower()

    metadata = {
        "package_ecosystem": "swift",
        "registry": "swift_package_index",
        "package_name": package_name,
        "package_key": package_key,
        "repository_url": repository_url,
        "package_url": package_url,
        "latest_version": latest_version,
        "version": latest_version,
        "stars": stars,
        "score": score,
        "keywords": _string_list(item.get("keywords") or item.get("tags")),
        "categories": _string_list(item.get("categories")),
        "license": _string_or_none(item.get("license")),
        "search_query": search_query,
        "query": search_query,
        "signal_kind": "package_metadata",
        "signal_role": "solution",
    }

    return Signal(
        id=_signal_id(package_key),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_name}@{latest_version}" if latest_version else package_name,
        content=description[:500],
        url=package_url,
        author=_owner(repository_url),
        published_at=updated_at,
        tags=tags,
        credibility=_credibility(stars=stars, score=score, updated_at=updated_at),
        metadata=metadata,
    )


def _package_name(item: dict, repository_url: str | None) -> str | None:
    for key in ("name", "package_name", "packageName", "title"):
        value = _string_or_none(item.get(key))
        if value:
            return value

    if repository_url:
        return repository_url.rstrip("/").rsplit("/", 1)[-1] or None
    return None


def _repository_url(item: dict) -> str | None:
    repository = item.get("repository")
    if isinstance(repository, dict):
        for key in ("url", "html_url", "repository_url"):
            value = _string_or_none(repository.get(key))
            if value:
                return value

    return _string_or_none(
        item.get("repository_url")
        or item.get("repositoryURL")
        or item.get("repo_url")
        or item.get("url")
    )


def _package_url(item: dict, package_name: str, repository_url: str | None) -> str:
    configured = _string_or_none(item.get("package_url") or item.get("packageURL") or item.get("spi_url"))
    if configured:
        return urljoin(SWIFT_PACKAGE_INDEX_BASE, configured)

    if repository_url:
        path = repository_url.removeprefix("https://github.com/").removeprefix(
            "http://github.com/"
        )
        if path != repository_url:
            return f"{SWIFT_PACKAGE_INDEX_BASE}/{quote(path.strip('/'), safe='/')}"

    return f"{SWIFT_PACKAGE_INDEX_BASE}/search?query={quote(package_name)}"


def _build_tags(item: dict, *, search_query: str) -> list[str]:
    raw_tags = ["swift", "swift-package-index", search_query]
    raw_tags.extend(_string_list(item.get("keywords") or item.get("tags")))
    raw_tags.extend(_string_list(item.get("categories")))
    license_name = _string_or_none(item.get("license"))
    if license_name:
        raw_tags.append(license_name)
    if _int_or_none(item.get("stars") or item.get("star_count") or item.get("github_stars")):
        raw_tags.append("package-popularity")

    seen: set[str] = set()
    tags: list[str] = []
    for tag in raw_tags:
        normalized = tag.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tags.append(normalized)
    return tags[:10]


def _matches_filters(signal: Signal, *, keywords: list[str], categories: list[str]) -> bool:
    metadata = signal.metadata
    haystack = {
        str(signal.title).lower(),
        str(signal.content).lower(),
        *(tag.lower() for tag in signal.tags),
        *(value.lower() for value in metadata.get("keywords", [])),
        *(value.lower() for value in metadata.get("categories", [])),
    }

    if keywords and not any(keyword.lower() in haystack for keyword in keywords):
        return False
    if categories and not any(category.lower() in haystack for category in categories):
        return False
    return True


def _credibility(
    *,
    stars: int | None,
    score: float | None,
    updated_at: datetime | None,
) -> float:
    star_score = min(math.log10((stars or 0) + 1) / 5, 0.5)
    search_score = min(max(score or 0.0, 0.0) / 10, 0.25)
    freshness_score = 0.0

    if updated_at is not None:
        age_days = (datetime.now(timezone.utc) - updated_at).days
        if age_days <= 30:
            freshness_score = 0.2
        elif age_days <= 180:
            freshness_score = 0.15
        elif age_days <= 365:
            freshness_score = 0.08

    return min(round(0.15 + star_score + search_score + freshness_score, 3), 1.0)


def _signal_id(package_key: str) -> str:
    digest = hashlib.sha1(package_key.encode()).hexdigest()[:12]
    return f"swift_package_index:{digest}"


def _owner(repository_url: str | None) -> str | None:
    if not repository_url:
        return None
    path = repository_url.rstrip("/").split("github.com/", 1)
    if len(path) == 2:
        owner = path[1].split("/", 1)[0].strip()
        return owner or None
    return None


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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _int_or_none(value: object) -> int | None:
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
