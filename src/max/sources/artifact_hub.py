"""Artifact Hub source adapter - cloud-native package adoption signals."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

ARTIFACT_HUB_BASE_URL = "https://artifacthub.io"
ARTIFACT_HUB_SEARCH_PATH = "/api/v1/packages/search"
_DEFAULT_QUERIES = ["kubernetes", "helm", "operator", "observability", "security"]
_DEFAULT_PACKAGE_TYPES = ["helm", "olm", "container", "krew", "kyverno"]


class ArtifactHubAdapter(SourceAdapter):
    """Fetch Artifact Hub package popularity and maintenance signals."""

    @property
    def name(self) -> str:
        return "artifact_hub"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def base_url(self) -> str:
        configured = self._config.get("base_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().rstrip("/")
        return ARTIFACT_HUB_BASE_URL

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def categories(self) -> list[str]:
        return _string_values(self._config.get("categories"))

    @property
    def package_types(self) -> list[str]:
        configured = self._config.get("package_types")
        if configured is None:
            configured = self._config.get("kinds")
        values = (
            _string_values(configured)
            if configured is not None
            else list(_DEFAULT_PACKAGE_TYPES)
        )
        return _dedupe_terms(values)

    @property
    def sort(self) -> str:
        return _string_or_none(self._config.get("sort")) or "relevance"

    @property
    def max_results(self) -> int | None:
        return _positive_int_or_none(self._config.get("max_results"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        target = max(0, limit)
        if self.max_results is not None:
            target = min(target, self.max_results)
        if target == 0:
            return []

        signals: list[Signal] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                if len(signals) >= target:
                    break
                await self._fetch_search(
                    client,
                    signals=signals,
                    seen=seen,
                    limit=target,
                    query=query,
                    categories=self.categories,
                    package_types=self.package_types,
                )

            if self.categories:
                for category in self.categories:
                    if len(signals) >= target:
                        break
                    await self._fetch_search(
                        client,
                        signals=signals,
                        seen=seen,
                        limit=target,
                        query=None,
                        categories=[category],
                        package_types=self.package_types,
                    )

        return signals[:target]

    async def _fetch_search(
        self,
        client: httpx.AsyncClient,
        *,
        signals: list[Signal],
        seen: set[str],
        limit: int,
        query: str | None,
        categories: list[str],
        package_types: list[str],
    ) -> None:
        offset = 0
        while len(signals) < limit:
            request_limit = min(60, max(1, limit - len(signals)))
            params: dict[str, object] = {
                "limit": request_limit,
                "offset": offset,
                "facets": "false",
                "sort": self.sort,
            }
            if query:
                params["ts_query_web"] = query
            if categories:
                params["category"] = categories
            if package_types:
                params["kind"] = package_types

            data = await self._fetch_json(
                client,
                self._search_url(),
                context=f"package search '{query or ','.join(categories) or 'all'}'",
                params=params,
            )
            items = _extract_packages(data)
            if not items:
                break

            before = len(signals)
            self._append_signals(
                signals,
                items,
                seen=seen,
                limit=limit,
                search_query=query,
                categories=categories,
            )

            if len(signals) == before or len(items) < request_limit:
                break
            offset += len(items)

    async def _fetch_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        context: str,
        params: dict[str, object],
    ) -> dict | list | None:
        try:
            resp = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                params=params,
                headers={"User-Agent": "max-artifact-hub-adapter/0.1"},
            )
            return resp.json()
        except AdapterFetchError as e:
            logger.warning(
                "%s: failed to fetch Artifact Hub data for %s: %s",
                self.name,
                context,
                e,
            )
        except ValueError as e:
            logger.warning(
                "%s: failed to parse JSON response for %s: %s",
                self.name,
                context,
                e,
            )
        return None

    def _search_url(self) -> str:
        return f"{self.base_url}{ARTIFACT_HUB_SEARCH_PATH}"

    def _append_signals(
        self,
        signals: list[Signal],
        items: list[dict],
        *,
        seen: set[str],
        limit: int,
        search_query: str | None,
        categories: list[str],
    ) -> None:
        for item in items:
            if len(signals) >= limit:
                break
            try:
                signal = _package_to_signal(
                    item,
                    adapter_name=self.name,
                    base_url=self.base_url,
                    search_query=search_query,
                    requested_categories=categories,
                )
                identity = _identity(signal.metadata)
                if identity in seen:
                    continue
                seen.add(identity)
                signals.append(signal)
            except (TypeError, ValueError) as e:
                logger.warning("%s: failed to parse Artifact Hub package item: %s", self.name, e)


def _package_to_signal(
    item: dict,
    *,
    adapter_name: str,
    base_url: str,
    search_query: str | None,
    requested_categories: list[str],
) -> Signal:
    package_id = _string_or_none(
        item.get("package_id") or item.get("packageID") or item.get("id")
    )
    name = _string_or_none(item.get("name") or item.get("normalized_name"))
    normalized_name = _string_or_none(item.get("normalized_name")) or name
    if name is None:
        raise ValueError("package missing name")

    repository = item.get("repository") if isinstance(item.get("repository"), dict) else {}
    repository_name = _string_or_none(
        repository.get("name")
        or repository.get("display_name")
        or item.get("repository_name")
        or item.get("repo_name")
    )
    repository_url = _string_or_none(
        repository.get("url") or repository.get("repository_url") or item.get("repository_url")
    )
    repository_id = _string_or_none(repository.get("repository_id") or item.get("repository_id"))
    organization = _string_or_none(
        repository.get("organization_name") or repository.get("org_name") or item.get("organization_name")
    )
    publisher = organization or _string_or_none(repository.get("user_alias") or item.get("user_alias"))
    package_type = _package_type(item, repository)
    category = _string_or_none(item.get("category") or item.get("category_id"))
    stars = _int_or_none(item.get("stars") or item.get("stars_count"))
    official = _bool_or_none(
        item.get("official") if item.get("official") is not None else repository.get("official")
    )
    verified_publisher = _bool_or_none(
        item.get("verified_publisher")
        if item.get("verified_publisher") is not None
        else repository.get("verified_publisher")
    )
    version = _string_or_none(item.get("version") or item.get("latest_version"))
    app_version = _string_or_none(item.get("app_version") or item.get("appVersion"))
    deprecated = _bool_or_none(item.get("deprecated"))
    updated_at = _parse_datetime(
        item.get("updated_at")
        or item.get("updatedAt")
        or item.get("last_updated")
        or item.get("lastUpdate")
        or item.get("created_at")
    )
    description = _string_or_none(item.get("description")) or name
    source_url = _source_url(
        item,
        base_url=base_url,
        package_type=package_type,
        repository_name=repository_name,
        package_name=normalized_name or name,
    )

    metadata = {
        "package_id": package_id,
        "name": name,
        "normalized_name": normalized_name,
        "package_type": package_type,
        "category": category,
        "version": version,
        "app_version": app_version,
        "stars": stars,
        "official": official,
        "verified_publisher": verified_publisher,
        "deprecated": deprecated,
        "repository": {
            "id": repository_id,
            "name": repository_name,
            "url": repository_url,
            "official": official,
            "verified_publisher": verified_publisher,
            "organization": organization,
            "publisher": publisher,
        },
        "repository_url": repository_url,
        "search_query": search_query,
        "requested_categories": requested_categories,
        "updated_at": updated_at.isoformat() if updated_at is not None else None,
        "signal_role": "market",
        "popularity": {"stars": stars, "official": official},
        "maintenance": {
            "updated_at": updated_at.isoformat() if updated_at is not None else None,
            "version": version,
            "app_version": app_version,
            "deprecated": deprecated,
        },
    }

    title = f"{name} ({package_type})" if package_type else name
    if version:
        title = f"{title}@{version}"

    return Signal(
        id=f"{adapter_name}:{_identity(metadata)}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=title,
        content=description[:500],
        url=source_url,
        author=publisher or repository_name,
        published_at=updated_at,
        tags=_tags(package_type=package_type, category=category, search_query=search_query),
        credibility=_credibility(
            stars=stars,
            official=official,
            verified_publisher=verified_publisher,
        ),
        metadata=metadata,
    )


def _extract_packages(data: dict | list | None) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("packages", "results", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _package_type(item: dict, repository: dict) -> str | None:
    value = (
        item.get("package_type")
        or item.get("packageType")
        or item.get("kind")
        or item.get("repository_kind")
        or repository.get("kind")
    )
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, int):
        return str(value)
    return None


def _source_url(
    item: dict,
    *,
    base_url: str,
    package_type: str | None,
    repository_name: str | None,
    package_name: str,
) -> str:
    for key in ("url", "package_url", "artifacthub_url", "html_url"):
        value = _string_or_none(item.get(key))
        if value:
            return value
    if package_type and repository_name:
        return (
            f"{base_url}/packages/{quote(package_type, safe='')}/"
            f"{quote(repository_name, safe='')}/{quote(package_name, safe='')}"
        )
    return f"{base_url}/packages/search?ts_query_web={quote(package_name, safe='')}"


def _tags(
    *,
    package_type: str | None,
    category: str | None,
    search_query: str | None,
) -> list[str]:
    values = ["artifact-hub", "cloud-native"]
    if package_type:
        values.append(package_type)
    if category:
        values.append(category)
    if search_query:
        values.append(search_query)
    return _dedupe_terms(values)


def _identity(metadata: dict) -> str:
    return "|".join(
        str(metadata.get(key) or "").lower()
        for key in ("package_id", "package_type", "normalized_name")
    )


def _credibility(
    *,
    stars: int | None,
    official: bool | None,
    verified_publisher: bool | None,
) -> float:
    star_score = min(math.log10((stars or 0) + 1) / 4, 0.55)
    official_score = 0.2 if official is True else 0.0
    verified_score = 0.15 if verified_publisher is True else 0.0
    return min(round(0.1 + star_score + official_score + verified_score, 3), 1.0)


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


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []
    return _dedupe_terms(
        [item.strip() for item in values if isinstance(item, str) and item.strip()]
    )


def _dedupe_terms(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _positive_int_or_none(value: object) -> int | None:
    parsed = _int_or_none(value)
    if parsed is None or parsed < 1:
        return None
    return parsed


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
