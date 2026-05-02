"""NuGet package activity source adapter."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

NUGET_SEARCH_API = "https://azuresearch-usnc.nuget.org/query"
NUGET_REGISTRATION_API = "https://api.nuget.org/v3/registration5-gz-semver2/{package_id}/index.json"
NUGET_PACKAGE_URL = "https://www.nuget.org/packages/{package_id}/{version}"
NUGET_PACKAGE_ROOT_URL = "https://www.nuget.org/packages/{package_id}"

_DEFAULT_QUERIES = ["semantic kernel", "openai", "mcp", "agent"]
_DEFAULT_PACKAGES = [
    "Microsoft.Extensions.AI",
    "Microsoft.SemanticKernel",
    "Azure.AI.OpenAI",
    "OpenAI",
    "ModelContextProtocol",
]


class NuGetPackageActivityAdapter(SourceAdapter):
    """Fetch NuGet package release, popularity, and metadata activity signals."""

    @property
    def name(self) -> str:
        return "nuget_package_activity"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def packages(self) -> list[str]:
        default = (
            _DEFAULT_PACKAGES
            if self._config.get("packages") is None and self._config.get("package_names") is None
            else []
        )
        return _dedupe(
            self._configured_terms("packages", [])
            + self._configured_terms("package_names", default)
        )

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", self._configured_terms("search_terms", _DEFAULT_QUERIES))

    @property
    def include_prerelease(self) -> bool:
        return bool(self._config.get("include_prerelease", False))

    @property
    def max_results_per_query(self) -> int:
        return max(_int_or_none(self._config.get("max_results_per_query")) or 10, 1)

    @property
    def timeout(self) -> float:
        try:
            timeout = float(self._config.get("timeout", 30))
        except (TypeError, ValueError):
            return 30.0
        return timeout if timeout > 0 else 30.0

    @property
    def search_url(self) -> str:
        value = self._config.get("search_url")
        return value.strip() if isinstance(value, str) and value.strip() else NUGET_SEARCH_API

    @property
    def registration_url_template(self) -> str:
        value = self._config.get("registration_url")
        return value.strip() if isinstance(value, str) and value.strip() else NUGET_REGISTRATION_API

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = max(limit, 0)
        if item_limit == 0:
            return []

        signals: list[Signal] = []
        seen_packages: set[str] = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for package_id in self.packages:
                if len(signals) >= item_limit:
                    break

                normalized = _normalized_package_id(package_id)
                if normalized is None or normalized.lower() in seen_packages:
                    continue

                registration = await self._fetch_registration(client, normalized)
                entries = await self._registration_entries(client, registration, package_id=normalized)
                signal = _signal_from_entries(
                    entries,
                    adapter_name=self.name,
                    package_id=normalized,
                )
                if signal is None:
                    continue

                seen_packages.add(signal.metadata["package_id"].lower())
                signals.append(signal)

            for query in self.queries:
                if len(signals) >= item_limit:
                    break

                payload = await self._fetch_search(
                    client,
                    query=query,
                    take=min(self.max_results_per_query, item_limit - len(signals)),
                )
                packages = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(packages, list):
                    continue

                for package in packages:
                    if len(signals) >= item_limit:
                        break
                    if not isinstance(package, dict):
                        continue

                    package_id = _string_or_none(package.get("id"))
                    if package_id is None or package_id.lower() in seen_packages:
                        continue

                    registration = await self._fetch_registration(client, package_id)
                    entries = await self._registration_entries(client, registration, package_id=package_id)
                    signal = _signal_from_entries(
                        entries,
                        adapter_name=self.name,
                        package_id=package_id,
                        search_package=package,
                        search_query=query,
                    )
                    if signal is None:
                        signal = parse_package_signal(
                            package,
                            adapter_name=self.name,
                            search_query=query,
                        )
                    if signal is None:
                        continue

                    seen_packages.add(signal.metadata["package_id"].lower())
                    signals.append(signal)

        return signals[:item_limit]

    async def _fetch_search(self, client: httpx.AsyncClient, *, query: str, take: int) -> dict | None:
        return await self._fetch_json(
            client,
            self.search_url,
            context=f"search query '{query}'",
            params={
                "q": query,
                "take": take,
                "prerelease": str(self.include_prerelease).lower(),
            },
        )

    async def _fetch_registration(self, client: httpx.AsyncClient, package_id: str) -> dict | None:
        encoded = quote(package_id.lower(), safe="")
        return await self._fetch_json(
            client,
            self.registration_url_template.format(package_id=encoded),
            context=f"package '{package_id}'",
        )

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object] | None = None,
    ) -> dict | None:
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                params=params,
                headers={"User-Agent": "max-nuget-package-activity-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch NuGet %s: %s", self.name, context, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for NuGet %s: %s", self.name, context, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse NuGet %s JSON: %s", self.name, context, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed NuGet response for %s", self.name, context)
            return None
        return payload

    async def _registration_entries(
        self,
        client: httpx.AsyncClient,
        registration: dict | None,
        *,
        package_id: str,
    ) -> list[dict]:
        if not isinstance(registration, dict):
            return []

        entries: list[dict] = []
        for page in registration.get("items") or []:
            if not isinstance(page, dict):
                continue

            page_items = page.get("items")
            if page_items is None and isinstance(page.get("@id"), str):
                page_payload = await self._fetch_json(
                    client,
                    page["@id"],
                    context=f"registration page for package '{package_id}'",
                )
                if isinstance(page_payload, dict):
                    page_items = page_payload.get("items")

            for item in page_items or []:
                if isinstance(item, dict) and isinstance(item.get("catalogEntry"), dict):
                    entries.append(item)

        return entries


def parse_package_signal(
    package: dict,
    *,
    adapter_name: str = "nuget_package_activity",
    search_query: str | None = None,
) -> Signal | None:
    """Normalize a NuGet search package entry into a Signal."""

    package_id = _string_or_none(package.get("id"))
    if package_id is None:
        return None

    version = _string_or_none(package.get("version")) or _string_or_none(package.get("latestVersion")) or ""
    published_at = _parse_datetime(package.get("published") or package.get("created") or package.get("lastUpdated"))
    description = _string_or_none(package.get("description")) or _string_or_none(package.get("summary")) or ""
    downloads = _int_or_none(package.get("totalDownloads")) or 0
    version_downloads = _version_downloads(package, version)
    tags = _build_tags(package.get("tags"), package_id=package_id, search_query=search_query)
    url = _package_url(package_id, version)

    metadata = {
        "signal_role": "market",
        "package_ecosystem": "nuget",
        "package_id": package_id,
        "package_name": package_id,
        "version": version,
        "latest_version": version,
        "published_at": published_at.isoformat() if published_at else None,
        "publish_date": published_at.isoformat() if published_at else None,
        "description": description,
        "downloads": downloads,
        "download_count": downloads,
        "version_downloads": version_downloads,
        "authors": _string_or_none(package.get("authors")),
        "owners": _string_list(package.get("owners")),
        "tags": tags,
        "project_url": _string_or_none(package.get("projectUrl")),
        "icon_url": _string_or_none(package.get("iconUrl")),
        "license_url": _string_or_none(package.get("licenseUrl")),
        "verified": bool(package.get("verified", False)),
        "search_query": search_query,
        "source_url": url,
        "signal_kind": "package_activity",
    }

    return Signal(
        id=f"{adapter_name}:{package_id}:{version or 'latest'}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_id}@{version}" if version else f"{package_id} NuGet package activity",
        content=_content(package_id, version, downloads, published_at, description),
        url=url,
        author=metadata["authors"],
        published_at=published_at,
        tags=tags,
        credibility=_credibility(
            downloads=downloads,
            version_downloads=version_downloads,
            published_at=published_at,
            verified=metadata["verified"],
        ),
        metadata=metadata,
    )


def _signal_from_entries(
    entries: list[dict],
    *,
    adapter_name: str,
    package_id: str,
    search_package: dict | None = None,
    search_query: str | None = None,
) -> Signal | None:
    entry = _latest_registration_entry(entries)
    if entry is None:
        return None

    catalog = entry.get("catalogEntry")
    if not isinstance(catalog, dict):
        return None

    package = dict(search_package or {})
    package.update(
        {
            "id": _string_or_none(catalog.get("id")) or package_id,
            "version": _string_or_none(catalog.get("version")) or _string_or_none(package.get("version")) or "",
            "description": _string_or_none(catalog.get("description")) or _string_or_none(package.get("description")),
            "authors": _string_or_none(catalog.get("authors")) or _string_or_none(package.get("authors")),
            "published": catalog.get("published"),
            "projectUrl": catalog.get("projectUrl") or package.get("projectUrl"),
            "tags": catalog.get("tags") or package.get("tags"),
        }
    )
    signal = parse_package_signal(package, adapter_name=adapter_name, search_query=search_query)
    if signal is None:
        return None

    signal.metadata["registration_url"] = entry.get("@id")
    signal.metadata["package_content_url"] = entry.get("packageContent") or catalog.get("packageContent")
    signal.metadata["deprecation"] = catalog.get("deprecation")
    signal.metadata["vulnerabilities"] = catalog.get("vulnerabilities")
    return signal


def _latest_registration_entry(entries: list[dict]) -> dict | None:
    if not entries:
        return None

    return max(
        entries,
        key=lambda item: (
            _parse_datetime((item.get("catalogEntry") or {}).get("published"))
            or datetime.min.replace(tzinfo=timezone.utc),
            str((item.get("catalogEntry") or {}).get("version") or ""),
        ),
    )


def _content(
    package_id: str,
    version: str,
    downloads: int,
    published_at: datetime | None,
    description: str,
) -> str:
    version_text = f" version {version}" if version else ""
    published_text = f" Published {published_at.date().isoformat()}." if published_at else ""
    summary = f"{package_id}{version_text} has {downloads:,} total downloads on NuGet.{published_text}"
    if description:
        return f"{summary} {description}"[:1000]
    return summary


def _package_url(package_id: str, version: str) -> str:
    if version:
        return NUGET_PACKAGE_URL.format(package_id=quote(package_id, safe=""), version=quote(version, safe=""))
    return NUGET_PACKAGE_ROOT_URL.format(package_id=quote(package_id, safe=""))


def _version_downloads(package: dict, version: str) -> int | None:
    for item in package.get("versions") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("version") or "").lower() == version.lower():
            return _int_or_none(item.get("downloads"))
    return None


def _build_tags(value: object, *, package_id: str, search_query: str | None = None) -> list[str]:
    raw_tags = ["nuget", "dotnet", package_id]
    if isinstance(value, str):
        raw_tags.extend(part.strip() for part in value.replace(",", " ").split())
    elif isinstance(value, list):
        raw_tags.extend(item.strip() for item in value if isinstance(item, str))
    if search_query:
        raw_tags.append(search_query)

    seen: set[str] = set()
    tags: list[str] = []
    for tag in raw_tags:
        normalized = tag.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tags.append(normalized)
    return tags[:12]


def _credibility(
    *,
    downloads: int,
    version_downloads: int | None,
    published_at: datetime | None,
    verified: bool,
) -> float:
    downloads_score = min(math.log10(downloads + 1) / 7, 0.5)
    version_score = min(math.log10((version_downloads or 0) + 1) / 6, 0.15)
    verified_score = 0.1 if verified else 0.0
    freshness_score = 0.0
    if published_at is not None:
        age_days = (datetime.now(timezone.utc) - published_at).days
        if age_days <= 30:
            freshness_score = 0.2
        elif age_days <= 180:
            freshness_score = 0.15
        elif age_days <= 365:
            freshness_score = 0.1
        elif age_days <= 730:
            freshness_score = 0.05
    return min(round(0.15 + downloads_score + version_score + verified_score + freshness_score, 3), 1.0)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
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
    if isinstance(value, str):
        return [item.strip() for item in value.replace(",", " ").split() if item.strip()]
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def _normalized_package_id(value: object) -> str | None:
    return _string_or_none(value)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped
