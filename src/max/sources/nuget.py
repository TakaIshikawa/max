"""NuGet source adapter — .NET ecosystem package activity."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

NUGET_SEARCH = "https://azuresearch-usnc.nuget.org/query"
NUGET_REGISTRATION = "https://api.nuget.org/v3/registration5-gz-semver2/{package_id}/index.json"
NUGET_PACKAGE_PAGE = "https://www.nuget.org/packages/{package_id}/{version}"

_DEFAULT_QUERIES = ["ai", "llm", "agent", "mcp", "openai"]
_DEFAULT_PACKAGE_NAMES = [
    "Microsoft.Extensions.AI",
    "Microsoft.SemanticKernel",
    "Azure.AI.OpenAI",
    "OpenAI",
    "ModelContextProtocol",
]


class NuGetAdapter(SourceAdapter):
    """Fetch NuGet package metadata and recent version activity."""

    @property
    def name(self) -> str:
        return "nuget"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def package_names(self) -> list[str]:
        return self._configured_terms("package_names", _DEFAULT_PACKAGE_NAMES)

    @property
    def include_prerelease(self) -> bool:
        return bool(self._config.get("include_prerelease", False))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_packages: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for package_name in self.package_names:
                if len(signals) >= limit:
                    break

                package_id = package_name.strip()
                if not package_id:
                    continue

                registration = await self._fetch_registration(client, package_id)
                if registration is None:
                    continue

                signal = await self._signal_from_registration(
                    client,
                    package_id,
                    registration,
                    package_name=package_id,
                )
                if signal is None:
                    continue

                seen_packages.add(signal.metadata["package_id"].lower())
                signals.append(signal)

            for query in self.queries:
                if len(signals) >= limit:
                    break

                data = await self._fetch_json(
                    client,
                    NUGET_SEARCH,
                    context=f"query '{query}'",
                    params={
                        "q": query,
                        "take": min(10, limit - len(signals)),
                        "prerelease": str(self.include_prerelease).lower(),
                    },
                )
                if data is None:
                    continue

                for package in data.get("data", []):
                    if len(signals) >= limit:
                        break

                    package_id = _string_or_none(package.get("id"))
                    if package_id is None or package_id.lower() in seen_packages:
                        continue

                    registration = await self._fetch_registration(client, package_id)
                    signal = None
                    if registration is not None:
                        signal = await self._signal_from_registration(
                            client,
                            package_id,
                            registration,
                            search_package=package,
                            search_query=query,
                        )
                    if signal is None:
                        signal = _search_package_to_signal(
                            package,
                            adapter_name=self.name,
                            search_query=query,
                        )
                    if signal is None:
                        continue

                    seen_packages.add(signal.metadata["package_id"].lower())
                    signals.append(signal)

        return signals[:limit]

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object] | None = None,
    ) -> dict | None:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-nuget-adapter/0.1"},
            )
            return resp.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch NuGet data for %s: %s", self.name, context, e)
        except ValueError as e:
            logger.warning("%s: failed to parse JSON response for %s: %s", self.name, context, e)
        return None

    async def _fetch_registration(
        self,
        client: httpx.AsyncClient,
        package_id: str,
    ) -> dict | None:
        encoded_id = quote(package_id.lower(), safe="")
        return await self._fetch_json(
            client,
            NUGET_REGISTRATION.format(package_id=encoded_id),
            context=f"package '{package_id}'",
        )

    async def _signal_from_registration(
        self,
        client: httpx.AsyncClient,
        package_id: str,
        registration: dict,
        *,
        package_name: str | None = None,
        search_package: dict | None = None,
        search_query: str | None = None,
    ) -> Signal | None:
        entries = await self._registration_entries(client, registration, package_id=package_id)
        if not entries:
            return None

        entry = _latest_entry(entries)
        if entry is None:
            return None

        return _registration_entry_to_signal(
            entry,
            adapter_name=self.name,
            package_name=package_name,
            search_package=search_package,
            search_query=search_query,
        )

    async def _registration_entries(
        self,
        client: httpx.AsyncClient,
        registration: dict,
        *,
        package_id: str,
    ) -> list[dict]:
        entries: list[dict] = []
        for page in registration.get("items", []):
            if not isinstance(page, dict):
                continue

            page_items = page.get("items")
            if page_items is None and isinstance(page.get("@id"), str):
                data = await self._fetch_json(
                    client,
                    page["@id"],
                    context=f"registration page for package '{package_id}'",
                )
                if data is not None:
                    page_items = data.get("items")

            for item in page_items or []:
                if isinstance(item, dict) and isinstance(item.get("catalogEntry"), dict):
                    entries.append(item)

        return entries


def _registration_entry_to_signal(
    entry: dict,
    *,
    adapter_name: str,
    package_name: str | None = None,
    search_package: dict | None = None,
    search_query: str | None = None,
) -> Signal:
    catalog = entry.get("catalogEntry") or {}
    package_id = _string_or_none(catalog.get("id")) or _string_or_none(
        (search_package or {}).get("id")
    ) or package_name or ""
    version = _string_or_none(catalog.get("version")) or _string_or_none(
        (search_package or {}).get("version")
    ) or ""
    published_at = _parse_datetime(catalog.get("published"))
    downloads = _int_or_none((search_package or {}).get("totalDownloads")) or 0
    version_downloads = _version_downloads(search_package or {}, version)
    project_url = _string_or_none(catalog.get("projectUrl")) or _string_or_none(
        (search_package or {}).get("projectUrl")
    )
    evidence_url = NUGET_PACKAGE_PAGE.format(package_id=package_id, version=version)
    tags = _build_tags(
        catalog.get("tags") or (search_package or {}).get("tags"),
        search_query=search_query,
    )

    metadata = {
        "package_ecosystem": "nuget",
        "package_id": package_id,
        "version": version,
        "published_at": published_at.isoformat() if published_at else None,
        "publish_date": published_at.isoformat() if published_at else None,
        "downloads": downloads,
        "download_count": downloads,
        "version_downloads": version_downloads,
        "tags": tags,
        "project_url": project_url,
        "evidence_url": evidence_url,
        "registration_url": entry.get("@id"),
        "package_content_url": entry.get("packageContent") or catalog.get("packageContent"),
        "authors": _string_or_none(catalog.get("authors"))
        or _string_or_none((search_package or {}).get("authors")),
        "search_query": search_query,
        "package_name": package_name,
        "verified": bool((search_package or {}).get("verified", False)),
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_id}@{version}" if version else package_id,
        content=str(catalog.get("description") or (search_package or {}).get("description") or package_id)[:500],
        url=evidence_url,
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


def _search_package_to_signal(
    package: dict,
    *,
    adapter_name: str,
    search_query: str,
) -> Signal | None:
    package_id = _string_or_none(package.get("id"))
    if package_id is None:
        return None

    version = _string_or_none(package.get("version")) or ""
    downloads = _int_or_none(package.get("totalDownloads")) or 0
    version_downloads = _version_downloads(package, version)
    project_url = _string_or_none(package.get("projectUrl"))
    evidence_url = NUGET_PACKAGE_PAGE.format(package_id=package_id, version=version)
    tags = _build_tags(package.get("tags"), search_query=search_query)

    metadata = {
        "package_ecosystem": "nuget",
        "package_id": package_id,
        "version": version,
        "published_at": None,
        "publish_date": None,
        "downloads": downloads,
        "download_count": downloads,
        "version_downloads": version_downloads,
        "tags": tags,
        "project_url": project_url,
        "evidence_url": evidence_url,
        "registration_url": None,
        "package_content_url": None,
        "authors": _string_or_none(package.get("authors")),
        "search_query": search_query,
        "package_name": None,
        "verified": bool(package.get("verified", False)),
    }

    return Signal(
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_id}@{version}" if version else package_id,
        content=str(package.get("description") or package_id)[:500],
        url=evidence_url,
        author=metadata["authors"],
        published_at=None,
        tags=tags,
        credibility=_credibility(
            downloads=downloads,
            version_downloads=version_downloads,
            published_at=None,
            verified=metadata["verified"],
        ),
        metadata=metadata,
    )


def _latest_entry(entries: list[dict]) -> dict | None:
    candidates = [entry for entry in entries if isinstance(entry.get("catalogEntry"), dict)]
    if not candidates:
        return None

    return max(
        candidates,
        key=lambda entry: (
            _parse_datetime((entry.get("catalogEntry") or {}).get("published")) or datetime.min.replace(
                tzinfo=timezone.utc
            ),
            str((entry.get("catalogEntry") or {}).get("version") or ""),
        ),
    )


def _version_downloads(package: dict, version: str) -> int | None:
    for item in package.get("versions") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("version") or "").lower() == version.lower():
            return _int_or_none(item.get("downloads"))
    return None


def _build_tags(value: object, *, search_query: str | None = None) -> list[str]:
    raw_tags: list[str] = []
    if isinstance(value, str):
        raw_tags.extend(part.strip() for part in value.replace(",", " ").split())
    elif isinstance(value, list):
        raw_tags.extend(item.strip() for item in value if isinstance(item, str))

    if search_query:
        raw_tags.append(search_query)

    seen: set[str] = set()
    tags: list[str] = []
    for tag in raw_tags:
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags[:10]


def _credibility(
    *,
    downloads: int,
    version_downloads: int | None,
    published_at: datetime | None,
    verified: bool,
) -> float:
    downloads_score = min(math.log10(downloads + 1) / 7, 0.55)
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

    return min(round(0.1 + downloads_score + version_score + verified_score + freshness_score, 3), 1.0)


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
