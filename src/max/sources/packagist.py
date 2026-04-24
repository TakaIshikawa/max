"""Packagist source adapter - PHP ecosystem package metadata and activity."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

PACKAGIST_SEARCH = "https://packagist.org/search.json"
PACKAGIST_DETAILS = "https://repo.packagist.org/p2/{package_name}.json"
PACKAGIST_PACKAGE_PAGE = "https://packagist.org/packages/{package_name}"

_DEFAULT_QUERIES = ["laravel", "symfony", "wordpress", "ai", "api"]


class PackagistAdapter(SourceAdapter):
    """Fetch Packagist package popularity, repository, and release activity signals."""

    @property
    def name(self) -> str:
        return "packagist"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def include_maintenance(self) -> bool:
        return bool(self._config.get("include_maintenance", True))

    @property
    def active_release_days(self) -> int:
        return max(int(self._config.get("active_release_days", 365)), 1)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_packages: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                if len(signals) >= limit:
                    break

                search_data = await self._fetch_search(client, query=query, limit=limit - len(signals))
                if search_data is None:
                    continue

                for search_package in search_data.get("results", []):
                    if len(signals) >= limit:
                        break
                    if not isinstance(search_package, dict):
                        continue

                    package_name = _string_or_none(search_package.get("name"))
                    if package_name is None:
                        continue

                    normalized_name = package_name.lower()
                    if normalized_name in seen_packages:
                        continue
                    seen_packages.add(normalized_name)

                    details = await self._fetch_details(client, package_name)
                    package = _merge_package_data(search_package, details)
                    package_signal = _package_to_signal(
                        package,
                        adapter_name=self.name,
                        search_query=query,
                        active_release_days=self.active_release_days,
                    )
                    if package_signal is None:
                        continue

                    signals.append(package_signal)

                    if (
                        self.include_maintenance
                        and len(signals) < limit
                        and _is_maintained(package, active_release_days=self.active_release_days)
                    ):
                        maintenance_signal = _maintenance_signal(
                            package,
                            adapter_name=self.name,
                            search_query=query,
                            base_credibility=package_signal.credibility,
                        )
                        if maintenance_signal is not None:
                            signals.append(maintenance_signal)

        return signals[:limit]

    async def _fetch_search(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        limit: int,
    ) -> dict | None:
        try:
            resp = await fetch_with_retry(
                PACKAGIST_SEARCH,
                client,
                adapter_name=self.name,
                params={"q": query, "per_page": min(15, max(limit, 1))},
                headers={"User-Agent": "max-packagist-adapter/0.1"},
            )
            data = resp.json()
            return data if isinstance(data, dict) else None
        except AdapterFetchError as e:
            logger.warning(
                "%s: failed to fetch Packagist search results for query '%s': %s",
                self.name,
                query,
                e,
            )
        except ValueError as e:
            logger.warning(
                "%s: failed to parse Packagist search response for query '%s': %s",
                self.name,
                query,
                e,
            )
        return None

    async def _fetch_details(self, client: httpx.AsyncClient, package_name: str) -> dict | None:
        encoded_name = quote(package_name, safe="/")
        try:
            resp = await fetch_with_retry(
                PACKAGIST_DETAILS.format(package_name=encoded_name),
                client,
                adapter_name=self.name,
                headers={"User-Agent": "max-packagist-adapter/0.1"},
            )
            data = resp.json()
            if not isinstance(data, dict):
                return None
            packages = data.get("packages")
            versions = packages.get(package_name, []) if isinstance(packages, dict) else []
            return {"versions": versions} if isinstance(versions, list) else None
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Packagist details for '%s': %s", self.name, package_name, e)
        except ValueError as e:
            logger.warning("%s: failed to parse Packagist details for '%s': %s", self.name, package_name, e)
        return None


def _merge_package_data(search_package: dict, details: dict | None) -> dict:
    package = dict(search_package)
    versions = (details or {}).get("versions")
    if isinstance(versions, list):
        package["versions"] = versions
        latest = _latest_version(versions)
        if latest is not None:
            package["latest_version_data"] = latest
            package.setdefault("description", latest.get("description"))
            package.setdefault("repository", _repository_url(latest))
    return package


def _package_to_signal(
    package: dict,
    *,
    adapter_name: str,
    search_query: str,
    active_release_days: int,
) -> Signal | None:
    package_name = _string_or_none(package.get("name"))
    if package_name is None:
        return None

    if _is_abandoned(package):
        return None

    latest = package.get("latest_version_data") if isinstance(package.get("latest_version_data"), dict) else {}
    version = _string_or_none(latest.get("version")) or _string_or_none(package.get("version")) or ""
    released_at = _parse_datetime(latest.get("time") or package.get("time"))
    downloads = _download_count(package.get("downloads"), "total")
    monthly_downloads = _download_count(package.get("downloads"), "monthly")
    daily_downloads = _download_count(package.get("downloads"), "daily")
    stars = _int_or_none(package.get("github_stars")) or _int_or_none(package.get("stars")) or 0
    favers = _int_or_none(package.get("favers")) or 0
    repository_url = _string_or_none(package.get("repository")) or _repository_url(latest)
    latest_version = version
    tags = _build_tags(
        package,
        latest=latest,
        search_query=search_query,
        active_release_days=active_release_days,
    )

    metadata = {
        "package_ecosystem": "packagist",
        "package_name": package_name,
        "packagist_name": package_name,
        "version": latest_version,
        "latest_version": latest_version,
        "released_at": released_at.isoformat() if released_at else None,
        "downloads": downloads,
        "download_count": downloads,
        "monthly_downloads": monthly_downloads,
        "daily_downloads": daily_downloads,
        "favers": favers,
        "stars": stars,
        "github_stars": _int_or_none(package.get("github_stars")),
        "repository_url": repository_url,
        "homepage": _string_or_none(latest.get("homepage") or package.get("homepage")),
        "type": _string_or_none(latest.get("type") or package.get("type")),
        "license": _string_list(latest.get("license")),
        "keywords": _string_list(latest.get("keywords") or package.get("keywords")),
        "search_query": search_query,
        "signal_kind": "package_metadata",
        "signal_role": "solution",
        "maintained": _is_maintained(package, active_release_days=active_release_days),
    }

    return Signal(
        id=_signal_id(package_name, latest_version, "package"),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_name}@{latest_version}" if latest_version else package_name,
        content=(_string_or_none(package.get("description")) or package_name)[:500],
        url=_string_or_none(package.get("url")) or PACKAGIST_PACKAGE_PAGE.format(package_name=package_name),
        author=_author(latest),
        published_at=released_at,
        tags=tags,
        credibility=_credibility(
            downloads=downloads,
            monthly_downloads=monthly_downloads,
            stars=stars,
            favers=favers,
            released_at=released_at,
        ),
        metadata=metadata,
    )


def _maintenance_signal(
    package: dict,
    *,
    adapter_name: str,
    search_query: str,
    base_credibility: float,
) -> Signal | None:
    package_name = _string_or_none(package.get("name"))
    latest = package.get("latest_version_data") if isinstance(package.get("latest_version_data"), dict) else {}
    if package_name is None or not latest:
        return None

    version = _string_or_none(latest.get("version")) or ""
    released_at = _parse_datetime(latest.get("time"))
    repository_url = _string_or_none(package.get("repository")) or _repository_url(latest)
    downloads = _download_count(package.get("downloads"), "total")
    monthly_downloads = _download_count(package.get("downloads"), "monthly")
    stars = _int_or_none(package.get("github_stars")) or _int_or_none(package.get("stars")) or 0

    return Signal(
        id=_signal_id(package_name, version, "maintenance"),
        source_type=SignalSourceType.TRENDING,
        source_adapter=adapter_name,
        title=f"{package_name} maintenance activity",
        content=_maintenance_content(package_name, version, released_at, monthly_downloads, stars),
        url=_string_or_none(package.get("url")) or PACKAGIST_PACKAGE_PAGE.format(package_name=package_name),
        author=_author(latest),
        published_at=released_at,
        tags=_dedupe_tags(["php", "packagist", search_query, "maintenance", "release-activity"]),
        credibility=max(base_credibility, 0.55),
        metadata={
            "package_ecosystem": "packagist",
            "package_name": package_name,
            "packagist_name": package_name,
            "version": version,
            "latest_version": version,
            "released_at": released_at.isoformat() if released_at else None,
            "downloads": downloads,
            "download_count": downloads,
            "monthly_downloads": monthly_downloads,
            "stars": stars,
            "repository_url": repository_url,
            "search_query": search_query,
            "signal_kind": "maintenance_activity",
            "signal_role": "solution",
        },
    )


def _latest_version(versions: list[dict]) -> dict | None:
    candidates = [
        version
        for version in versions
        if isinstance(version, dict)
        and _string_or_none(version.get("version")) is not None
        and not str(version.get("version")).lower().startswith("dev-")
    ]
    if not candidates:
        candidates = [version for version in versions if isinstance(version, dict)]
    if not candidates:
        return None

    return max(
        candidates,
        key=lambda version: (
            _parse_datetime(version.get("time")) or datetime.min.replace(tzinfo=timezone.utc),
            str(version.get("version_normalized") or version.get("version") or ""),
        ),
    )


def _build_tags(
    package: dict,
    *,
    latest: dict,
    search_query: str,
    active_release_days: int,
) -> list[str]:
    tags: list[str] = ["php", "packagist", search_query]
    tags.extend(_string_list(latest.get("keywords") or package.get("keywords")))
    tags.extend(_string_list(latest.get("license")))

    if _download_count(package.get("downloads"), "total"):
        tags.append("package-popularity")
    if _string_or_none(package.get("repository")) or _repository_url(latest):
        tags.append("repository-metadata")
    if _is_maintained(package, active_release_days=active_release_days):
        tags.append("maintained")

    return _dedupe_tags(tags)


def _credibility(
    *,
    downloads: int,
    monthly_downloads: int | None,
    stars: int,
    favers: int,
    released_at: datetime | None,
) -> float:
    downloads_score = min(math.log10(downloads + 1) / 8, 0.45)
    monthly_score = min(math.log10((monthly_downloads or 0) + 1) / 7, 0.2)
    repository_score = min(math.log10(stars + 1) / 5, 0.15)
    favers_score = min(math.log10(favers + 1) / 5, 0.1)
    freshness_score = 0.0

    if released_at is not None:
        age_days = (datetime.now(timezone.utc) - released_at).days
        if age_days <= 30:
            freshness_score = 0.2
        elif age_days <= 180:
            freshness_score = 0.15
        elif age_days <= 365:
            freshness_score = 0.1
        elif age_days <= 730:
            freshness_score = 0.05

    return min(round(0.1 + downloads_score + monthly_score + repository_score + favers_score + freshness_score, 3), 1.0)


def _is_maintained(package: dict, *, active_release_days: int) -> bool:
    latest = package.get("latest_version_data") if isinstance(package.get("latest_version_data"), dict) else {}
    released_at = _parse_datetime(latest.get("time") if latest else package.get("time"))
    if released_at is not None:
        age_days = (datetime.now(timezone.utc) - released_at).days
        if age_days <= active_release_days:
            return True
    return (_download_count(package.get("downloads"), "monthly") or 0) >= 10_000


def _is_abandoned(package: dict) -> bool:
    abandoned = package.get("abandoned")
    return bool(abandoned) and not isinstance(abandoned, str)


def _repository_url(version: dict) -> str | None:
    source = version.get("source") if isinstance(version.get("source"), dict) else {}
    support = version.get("support") if isinstance(version.get("support"), dict) else {}
    return _string_or_none(source.get("url")) or _string_or_none(support.get("source"))


def _maintenance_content(
    package_name: str,
    version: str,
    released_at: datetime | None,
    monthly_downloads: int | None,
    stars: int,
) -> str:
    parts = [f"{package_name} released {version}" if version else f"{package_name} has release activity"]
    if released_at is not None:
        parts.append(f"on {released_at.date().isoformat()}")
    if monthly_downloads is not None:
        parts.append(f"with {monthly_downloads} monthly downloads")
    if stars:
        parts.append(f"and {stars} repository stars")
    return " ".join(parts) + "."


def _signal_id(package_name: str, version: str, kind: str) -> str:
    normalized_name = package_name.strip().lower()
    normalized_version = version.strip().lower() or "unknown"
    return f"packagist:{normalized_name}:{normalized_version}:{kind}"


def _author(version: dict) -> str | None:
    authors = version.get("authors")
    if not isinstance(authors, list):
        return None
    names = [
        author.get("name").strip()
        for author in authors
        if isinstance(author, dict) and isinstance(author.get("name"), str) and author.get("name").strip()
    ]
    return ", ".join(names[:3]) if names else None


def _download_count(value: object, key: str) -> int:
    if not isinstance(value, dict):
        return 0
    return _int_or_none(value.get(key)) or 0


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


def _dedupe_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for tag in tags:
        normalized = tag.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]
