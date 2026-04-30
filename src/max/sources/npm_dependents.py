"""npm dependents source adapter - reverse-dependency adoption signals."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

NPM_API_URL = "https://registry.npmjs.org"
NPM_PACKAGE_URL = "https://www.npmjs.com/package/{package}"


class NpmDependentsAdapter(SourceAdapter):
    """Fetch npm reverse-dependency metadata from npm-compatible endpoints."""

    @property
    def name(self) -> str:
        return "npm_dependents"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def package_names(self) -> list[str]:
        return self._configured_terms("package_names", [])

    @property
    def max_dependents_per_package(self) -> int:
        value = self._config.get("max_dependents_per_package", self._config.get("max_items", 30))
        return max(int(value), 1)

    @property
    def npm_api_url(self) -> str:
        configured = str(self._config.get("npm_api_url", NPM_API_URL)).strip()
        return (configured or NPM_API_URL).rstrip("/")

    @property
    def timeout(self) -> float:
        return float(self._config.get("timeout", 30))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_pairs: set[tuple[str, str]] = set()
        item_limit = max(limit, 0)
        if item_limit == 0:
            return signals

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for source_package in self.package_names:
                if len(signals) >= item_limit:
                    break

                normalized_source = _normalize_package_name(source_package)
                if not normalized_source:
                    continue

                payload = await self._fetch_dependents(
                    client,
                    normalized_source,
                    limit=min(self.max_dependents_per_package, item_limit - len(signals)),
                )
                if payload is None:
                    continue

                package_count = 0
                for row in _iter_dependent_rows(payload):
                    if len(signals) >= item_limit or package_count >= self.max_dependents_per_package:
                        break

                    signal = _dependent_to_signal(
                        row,
                        source_package=normalized_source,
                        adapter_name=self.name,
                        api_url=_dependents_api_url(
                            normalized_source,
                            limit=min(self.max_dependents_per_package, item_limit - len(signals)),
                            base_url=self.npm_api_url,
                        ),
                    )
                    if signal is None:
                        logger.warning(
                            "%s: malformed dependent row for %s",
                            self.name,
                            normalized_source,
                        )
                        continue

                    key = (
                        signal.metadata["source_package"],
                        signal.metadata["dependent_package"],
                    )
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    signals.append(signal)
                    package_count += 1

        return signals[:item_limit]

    async def _fetch_dependents(
        self,
        client: httpx.AsyncClient,
        package: str,
        *,
        limit: int,
    ) -> dict | list | None:
        url = _dependents_api_url(package, limit=limit, base_url=self.npm_api_url)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-npm-dependents-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch dependents for %s: %s", self.name, package, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, package, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse dependents for %s: %s", self.name, package, e)
            return None

        if not isinstance(payload, (dict, list)):
            logger.warning("%s: malformed dependents response for %s", self.name, package)
            return None
        return payload


def _dependents_api_url(package: str, *, limit: int, base_url: str) -> str:
    if "{package}" in base_url or "{limit}" in base_url:
        return base_url.format(package=quote(package, safe="@/"), limit=limit)

    search_text = quote(f"dependencies:{package}", safe=":@/")
    return f"{base_url}/-/v1/search?text={search_text}&size={limit}"


def _iter_dependent_rows(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    for key in ("dependents", "objects", "packages", "results", "rows", "data"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _dependent_to_signal(
    row: dict,
    *,
    source_package: str,
    adapter_name: str,
    api_url: str,
) -> Signal | None:
    package = _package_payload(row)
    dependent_package = _normalize_package_name(
        package.get("name") or package.get("package") or package.get("package_name")
    )
    if not dependent_package:
        return None

    version = _string_or_none(package.get("version") or package.get("latest") or package.get("latest_version"))
    description = _string_or_none(package.get("description")) or dependent_package
    downloads = _int_or_none(
        package.get("downloads")
        or package.get("weekly_downloads")
        or package.get("downloads_weekly")
        or package.get("monthly_downloads")
    )
    dependent_url = _package_url(dependent_package)
    source_url = _package_url(source_package)
    published_at = _parse_datetime(package.get("date") or package.get("published_at"))
    keywords = _string_list(package.get("keywords"))

    metadata = {
        "signal_role": "market",
        "signal_kind": "reverse_dependency",
        "evidence_type": "ecosystem_adoption",
        "package_ecosystem": "npm",
        "source_package": source_package,
        "source_package_url": source_url,
        "dependent_package": dependent_package,
        "dependent_package_url": dependent_url,
        "package_name": dependent_package,
        "npm_name": dependent_package,
        "version": version,
        "latest_version": version,
        "downloads": downloads,
        "weekly_downloads": _int_or_none(package.get("weekly_downloads") or package.get("downloads_weekly")),
        "monthly_downloads": _int_or_none(package.get("monthly_downloads")),
        "repository_url": _repository_url(package.get("repository")),
        "homepage": _string_or_none(package.get("homepage")),
        "api_url": api_url,
        "source_url": dependent_url,
    }

    return Signal(
        id=_signal_id(source_package, dependent_package),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{dependent_package} depends on {source_package}",
        content=_content(
            dependent_package,
            source_package=source_package,
            description=description,
            version=version,
            downloads=downloads,
        ),
        url=dependent_url,
        author=_publisher(package),
        published_at=published_at,
        tags=_build_tags(source_package, dependent_package, keywords=keywords),
        credibility=_credibility(downloads=downloads),
        metadata=metadata,
    )


def _package_payload(row: dict) -> dict:
    for key in ("package", "dependent", "metadata"):
        value = row.get(key)
        if isinstance(value, dict):
            return value
    return row


def _package_url(package: str) -> str:
    return NPM_PACKAGE_URL.format(package=quote(package, safe="@/"))


def _signal_id(source_package: str, dependent_package: str) -> str:
    return f"npm-dependents:{source_package}:{dependent_package}"


def _content(
    dependent_package: str,
    *,
    source_package: str,
    description: str,
    version: str | None,
    downloads: int | None,
) -> str:
    details = f"{dependent_package} depends on {source_package}."
    if version:
        details += f" Latest version: {version}."
    if downloads is not None:
        details += f" Downloads: {downloads:,}."
    if description and description != dependent_package:
        details += f" {description}"
    return details


def _build_tags(source_package: str, dependent_package: str, *, keywords: list[str]) -> list[str]:
    tags = [
        "javascript",
        "npm",
        "registry",
        "reverse-dependency",
        "ecosystem-adoption",
    ]
    tags.extend(_package_parts(source_package))
    tags.extend(_package_parts(dependent_package))
    tags.extend(keywords)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = tag.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _package_parts(package: str) -> list[str]:
    return [part for part in re.split(r"[/@._-]+", package.lower()) if part]


def _credibility(*, downloads: int | None) -> float:
    if downloads is None:
        return 0.35
    return min(round(0.35 + min(math.log10(downloads + 1) / 10, 0.55), 3), 1.0)


def _publisher(package: dict) -> str | None:
    publisher = package.get("publisher") or package.get("author")
    if isinstance(publisher, dict):
        return _string_or_none(publisher.get("username") or publisher.get("name"))
    return _string_or_none(publisher)


def _repository_url(value: object) -> str | None:
    if isinstance(value, dict):
        return _string_or_none(value.get("url"))
    return _string_or_none(value)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_package_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
