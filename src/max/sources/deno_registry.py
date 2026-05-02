"""Deno/JSR package registry source adapter."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import datetime
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

JSR_API_BASE = "https://api.jsr.io"
JSR_REGISTRY_BASE = "https://jsr.io"

_DEFAULT_QUERIES = ["deno", "typescript", "web framework", "cli", "mcp"]
_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "max-deno-registry-adapter/0.1",
}


class DenoRegistryAdapter(SourceAdapter):
    """Fetch Deno ecosystem package signals from JSR."""

    @property
    def name(self) -> str:
        return "deno_registry"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", _DEFAULT_QUERIES)

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", [])

    @property
    def package_names(self) -> list[str]:
        return self._configured_terms("package_names", self._configured_terms("packages", []))

    @property
    def max_results(self) -> int:
        return max(_int_or_none(self._config.get("max_results")) or 10, 1)

    @property
    def api_base_url(self) -> str:
        configured = str(self._config.get("api_base_url", JSR_API_BASE)).strip()
        return (configured or JSR_API_BASE).rstrip("/")

    @property
    def registry_base_url(self) -> str:
        configured = str(self._config.get("registry_base_url", JSR_REGISTRY_BASE)).strip()
        return (configured or JSR_REGISTRY_BASE).rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        item_limit = max(limit, 0)
        if item_limit == 0:
            return signals

        async with httpx.AsyncClient(timeout=30) as client:
            for package_name in self.package_names:
                if len(signals) >= item_limit:
                    break

                specifier = _parse_package_specifier(package_name)
                if specifier is None:
                    logger.warning("%s: invalid Deno package name '%s'", self.name, package_name)
                    continue

                data = await self._fetch_package_metadata(client, specifier=specifier)
                if data is None:
                    continue

                signal = _package_to_signal(
                    data,
                    adapter_name=self.name,
                    registry_base_url=self.registry_base_url,
                    search_query=None,
                    lookup_type="package",
                    fallback_specifier=specifier,
                )
                if signal is None:
                    continue
                dedupe_key = signal.metadata["package_specifier"].lower()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                signals.append(signal)

            for query in [*self.queries, *self.categories]:
                if len(signals) >= item_limit:
                    break

                per_query_limit = min(self.max_results, item_limit - len(signals))
                data = await self._fetch_search(client, query=query, limit=per_query_limit)
                if data is None:
                    continue

                for item in _extract_search_items(data)[:per_query_limit]:
                    if len(signals) >= item_limit:
                        break

                    signal = _package_to_signal(
                        item,
                        adapter_name=self.name,
                        registry_base_url=self.registry_base_url,
                        search_query=query,
                        lookup_type="search",
                        fallback_specifier=None,
                    )
                    if signal is None:
                        continue
                    dedupe_key = signal.metadata["package_specifier"].lower()
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    signals.append(signal)

        return signals[:item_limit]

    async def _fetch_search(
        self,
        client: httpx.AsyncClient,
        *,
        query: str,
        limit: int,
    ) -> dict | list | None:
        try:
            response = await fetch_with_retry(
                f"{self.api_base_url}/packages",
                client,
                adapter_name=self.name,
                params={"query": query, "limit": limit},
                headers=_DEFAULT_HEADERS,
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning(
                "%s: failed to fetch Deno package search results for query '%s': %s",
                self.name,
                query,
                e,
            )
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for Deno package query '%s': %s", self.name, query, e)
            return None
        except ValueError as e:
            logger.warning(
                "%s: failed to parse Deno package search results for query '%s': %s",
                self.name,
                query,
                e,
            )
            return None

        if isinstance(payload, (dict, list)):
            return payload
        logger.warning("%s: malformed Deno package search response for query '%s'", self.name, query)
        return None

    async def _fetch_package_metadata(
        self,
        client: httpx.AsyncClient,
        *,
        specifier: tuple[str, str],
    ) -> dict | None:
        scope, name = specifier
        url = _package_meta_url(scope, name, registry_base_url=self.registry_base_url)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                headers=_DEFAULT_HEADERS,
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning(
                "%s: failed to fetch Deno package metadata for '@%s/%s': %s",
                self.name,
                scope,
                name,
                e,
            )
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for Deno package '@%s/%s': %s", self.name, scope, name, e)
            return None
        except ValueError as e:
            logger.warning(
                "%s: failed to parse Deno package metadata for '@%s/%s': %s",
                self.name,
                scope,
                name,
                e,
            )
            return None

        if isinstance(payload, dict):
            return payload
        logger.warning("%s: malformed Deno package metadata for '@%s/%s'", self.name, scope, name)
        return None


def _extract_search_items(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    for key in ("items", "results", "packages", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _package_to_signal(
    item: dict,
    *,
    adapter_name: str,
    registry_base_url: str,
    search_query: str | None,
    lookup_type: str,
    fallback_specifier: tuple[str, str] | None,
) -> Signal | None:
    package = item.get("package") if isinstance(item.get("package"), dict) else item
    scope, name = _package_scope_name(package, fallback_specifier=fallback_specifier)
    if not scope or not name:
        return None

    specifier = f"@{scope}/{name}"
    versions = package.get("versions") if isinstance(package.get("versions"), dict) else {}
    latest_version = _latest_version(package, versions)
    latest = versions.get(latest_version) if latest_version and isinstance(versions.get(latest_version), dict) else {}
    description = (
        _string_or_none(package.get("description"))
        or _string_or_none(latest.get("description"))
        or specifier
    )
    runtime_tags = _string_list(package.get("runtimeCompat") or package.get("runtime_compat"))
    downloads = _int_or_none(
        package.get("downloads")
        or package.get("downloadCount")
        or package.get("weeklyDownloads")
        or package.get("downloads_week")
    )
    score = _float_or_none(package.get("score") or package.get("jsrScore") or package.get("scorePercent"))
    updated_at = _parse_datetime(
        package.get("updatedAt")
        or package.get("updated_at")
        or latest.get("publishedAt")
        or latest.get("published_at")
    )
    package_url = _package_page_url(scope, name, registry_base_url=registry_base_url)

    metadata = {
        "signal_role": "solution",
        "signal_kind": "package_metadata",
        "package_ecosystem": "deno",
        "registry": "jsr",
        "package_scope": scope,
        "package_name": name,
        "package_specifier": specifier,
        "deno_name": specifier,
        "latest_version": latest_version,
        "version": latest_version,
        "description": description,
        "downloads": downloads,
        "score": score,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "package_url": package_url,
        "source_url": package_url,
        "api_url": _package_meta_url(scope, name, registry_base_url=registry_base_url),
        "search_query": search_query,
        "query": search_query,
        "lookup_type": lookup_type,
    }

    return Signal(
        id=_signal_id(specifier),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{specifier}@{latest_version}" if latest_version else specifier,
        content=_content(specifier, description=description, downloads=downloads, score=score),
        url=package_url,
        published_at=updated_at,
        tags=_build_tags(package, search_query=search_query, runtime_tags=runtime_tags),
        credibility=_credibility(downloads=downloads, score=score),
        metadata=metadata,
    )


def _package_scope_name(
    package: dict,
    *,
    fallback_specifier: tuple[str, str] | None,
) -> tuple[str | None, str | None]:
    scope = _string_or_none(package.get("scope"))
    name = _string_or_none(package.get("name"))

    package_specifier = (
        _string_or_none(package.get("package"))
        or _string_or_none(package.get("specifier"))
        or _string_or_none(package.get("id"))
    )
    if package_specifier:
        parsed = _parse_package_specifier(package_specifier)
        if parsed is not None:
            scope = scope or parsed[0]
            name = name or parsed[1]

    if fallback_specifier is not None:
        scope = scope or fallback_specifier[0]
        name = name or fallback_specifier[1]

    if scope:
        scope = scope.removeprefix("@").strip()
    if name and "/" in name and name.startswith("@"):
        parsed = _parse_package_specifier(name)
        if parsed is not None:
            scope, name = parsed
    return scope, name


def _parse_package_specifier(value: str) -> tuple[str, str] | None:
    value = value.strip()
    match = re.match(r"^(?:jsr:)?@(?P<scope>[A-Za-z0-9_-]+)/(?P<name>[A-Za-z0-9_.-]+)$", value)
    if not match:
        return None
    return match.group("scope"), match.group("name")


def _latest_version(package: dict, versions: dict) -> str | None:
    for key in ("latestVersion", "latest_version", "version"):
        value = _string_or_none(package.get(key))
        if value:
            return value

    dist_tags = package.get("dist-tags") if isinstance(package.get("dist-tags"), dict) else {}
    value = _string_or_none(dist_tags.get("latest"))
    if value:
        return value

    if not versions:
        return None
    return sorted((version for version in versions if isinstance(version, str)), key=_version_key)[-1]


def _package_meta_url(scope: str, name: str, *, registry_base_url: str) -> str:
    return f"{registry_base_url}/@{quote(scope, safe='')}/{quote(name, safe='')}/meta.json"


def _package_page_url(scope: str, name: str, *, registry_base_url: str) -> str:
    return f"{registry_base_url}/@{quote(scope, safe='')}/{quote(name, safe='')}"


def _signal_id(specifier: str) -> str:
    digest = hashlib.sha1(specifier.strip().lower().encode()).hexdigest()[:12]
    return f"deno_registry:{digest}"


def _content(
    specifier: str,
    *,
    description: str,
    downloads: int | None,
    score: float | None,
) -> str:
    parts = [description[:350]]
    metrics: list[str] = []
    if downloads is not None:
        metrics.append(f"{downloads:,} downloads")
    if score is not None:
        metrics.append(f"{_score_percent(score):.0f}% JSR score")
    if metrics:
        parts.append(f"JSR reports {', '.join(metrics)} for {specifier}.")
    return " ".join(parts)[:500]


def _build_tags(package: dict, *, search_query: str | None, runtime_tags: list[str]) -> list[str]:
    tags = ["deno", "jsr", "typescript"]
    if search_query:
        tags.append(search_query)
    tags.extend(runtime_tags)
    tags.extend(_string_list(package.get("tags")))
    tags.extend(_string_list(package.get("keywords")))

    seen: set[str] = set()
    deduped: list[str] = []
    for tag in tags:
        normalized = tag.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _credibility(*, downloads: int | None, score: float | None) -> float:
    score_component = _score_percent(score) / 100 * 0.45 if score is not None else 0.2
    download_component = min(math.log10(downloads + 1) / 7, 0.45) if downloads is not None else 0.1
    return min(round(0.2 + score_component + download_component, 3), 1.0)


def _score_percent(score: float) -> float:
    return score * 100 if 0 <= score <= 1 else score


def _version_key(version: str) -> tuple:
    parts: list[int | str] = []
    for part in re.split(r"[.+-]", version):
        parts.append(int(part) if part.isdigit() else part)
    return tuple(parts)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


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


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[, ]+", value) if part.strip()]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
