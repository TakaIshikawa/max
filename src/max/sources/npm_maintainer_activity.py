"""npm maintainer activity source adapter -- package health and stewardship signals."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

NPM_API_URL = "https://registry.npmjs.org"
NPM_SEARCH_PATH = "-/v1/search"
NPM_PACKAGE_URL = "https://www.npmjs.com/package/{package}"


class NpmMaintainerActivityAdapter(SourceAdapter):
    """Fetch npm package metadata as maintainer activity and health signals."""

    @property
    def name(self) -> str:
        return "npm_maintainer_activity"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def packages(self) -> list[str]:
        return _dedupe_terms(
            self._configured_terms("packages", [])
            + self._configured_terms("package_names", [])
        )

    @property
    def queries(self) -> list[str]:
        return self._configured_terms("queries", self._configured_terms("search_terms", []))

    @property
    def max_results_per_query(self) -> int:
        value = self._config.get("max_results_per_query", self._config.get("max_items", 10))
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
        item_limit = max(limit, 0)
        if item_limit == 0:
            return signals

        package_sources: dict[str, str | None] = {
            package: None for package in (_normalize_package_name(value) for value in self.packages) if package
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for query in self.queries:
                if len(package_sources) >= item_limit:
                    break

                names = await self._search_package_names(
                    client,
                    query,
                    limit=min(self.max_results_per_query, item_limit - len(package_sources)),
                )
                for name in names:
                    package_sources.setdefault(name, query)
                    if len(package_sources) >= item_limit:
                        break

            seen_signals: set[str] = set()
            for package, query in package_sources.items():
                if len(signals) >= item_limit:
                    break

                payload = await self._fetch_package_metadata(client, package)
                if payload is None:
                    continue

                signal = _package_metadata_to_signal(
                    payload,
                    requested_package=package,
                    search_query=query,
                    adapter_name=self.name,
                    api_url=_package_api_url(package, base_url=self.npm_api_url),
                )
                if signal is None:
                    logger.warning("%s: malformed package metadata for %s", self.name, package)
                    continue
                if signal.id in seen_signals:
                    continue
                seen_signals.add(signal.id)
                signals.append(signal)

        return signals[:item_limit]

    async def _search_package_names(
        self,
        client: httpx.AsyncClient,
        query: str,
        *,
        limit: int,
    ) -> list[str]:
        if not query.strip() or limit <= 0:
            return []

        url = _search_api_url(base_url=self.npm_api_url)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                params={"text": query, "size": limit},
                headers={"User-Agent": "max-npm-maintainer-activity-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to search packages for query %r: %s", self.name, query, e)
            return []
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: search request failed for query %r: %s", self.name, query, e)
            return []
        except ValueError as e:
            logger.warning("%s: failed to parse search results for query %r: %s", self.name, query, e)
            return []

        if not isinstance(payload, dict):
            logger.warning("%s: malformed search results for query %r", self.name, query)
            return []

        names: list[str] = []
        for row in payload.get("objects", []):
            if not isinstance(row, dict):
                continue
            package = row.get("package")
            if not isinstance(package, dict):
                continue
            name = _normalize_package_name(package.get("name"))
            if name:
                names.append(name)
        return _dedupe_terms(names)

    async def _fetch_package_metadata(
        self,
        client: httpx.AsyncClient,
        package: str,
    ) -> dict | None:
        url = _package_api_url(package, base_url=self.npm_api_url)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-npm-maintainer-activity-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch package metadata for %s: %s", self.name, package, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: package metadata request failed for %s: %s", self.name, package, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse package metadata for %s: %s", self.name, package, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed package metadata for %s", self.name, package)
            return None
        return payload


def _package_metadata_to_signal(
    payload: dict,
    *,
    requested_package: str,
    search_query: str | None,
    adapter_name: str,
    api_url: str,
) -> Signal | None:
    package_name = _normalize_package_name(payload.get("name") or requested_package)
    if not package_name:
        return None

    dist_tags = payload.get("dist-tags") if isinstance(payload.get("dist-tags"), dict) else {}
    latest_version = _string_or_none(dist_tags.get("latest"))
    versions = payload.get("versions") if isinstance(payload.get("versions"), dict) else {}
    latest_payload = versions.get(latest_version) if latest_version and isinstance(versions.get(latest_version), dict) else {}

    maintainers = _people(payload.get("maintainers"))
    publisher = _person(latest_payload.get("_npmUser") or payload.get("_npmUser") or payload.get("publisher"))
    repository_url = _repository_url(payload.get("repository") or latest_payload.get("repository"))
    homepage = _string_or_none(payload.get("homepage") or latest_payload.get("homepage"))
    keywords = _string_list(payload.get("keywords") or latest_payload.get("keywords"))
    description = _string_or_none(payload.get("description") or latest_payload.get("description")) or package_name
    modified_at = _package_modified_time(payload, latest_version=latest_version)
    deprecated = _string_or_none(latest_payload.get("deprecated") or payload.get("deprecated"))

    maintainer_count = len(maintainers)
    health = {
        "maintainer_count": maintainer_count,
        "has_maintainers": maintainer_count > 0,
        "has_repository": repository_url is not None,
        "has_homepage": homepage is not None,
        "has_license": _string_or_none(payload.get("license") or latest_payload.get("license")) is not None,
        "has_readme": bool(_string_or_none(payload.get("readme"))),
        "deprecated": deprecated is not None,
        "version_count": len(versions),
    }

    return Signal(
        id=_signal_id(package_name),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_name} npm maintainer activity",
        content=_content(
            package_name,
            description=description,
            latest_version=latest_version,
            maintainer_count=maintainer_count,
            modified_at=modified_at,
            deprecated=deprecated,
            repository_url=repository_url,
        ),
        url=_package_url(package_name),
        author=publisher.get("name") if publisher else _first_person_name(maintainers),
        published_at=modified_at,
        tags=_build_tags(package_name, keywords=keywords, deprecated=deprecated is not None),
        credibility=_credibility(health),
        metadata={
            "signal_role": "market",
            "signal_kind": "maintainer_activity",
            "evidence_type": "package_health",
            "package_ecosystem": "npm",
            "package_name": package_name,
            "npm_name": package_name,
            "requested_package": requested_package,
            "search_query": search_query,
            "latest_version": latest_version,
            "maintainers": maintainers,
            "maintainer_count": maintainer_count,
            "publisher": publisher,
            "repository_url": repository_url,
            "homepage": homepage,
            "license": _string_or_none(payload.get("license") or latest_payload.get("license")),
            "keywords": keywords,
            "modified_at": modified_at.isoformat() if modified_at else None,
            "created_at": _iso_or_none(_parse_datetime(_time_value(payload, "created"))),
            "deprecated": deprecated,
            "version_count": len(versions),
            "health_indicators": health,
            "package_url": _package_url(package_name),
            "api_url": api_url,
            "source_url": _package_url(package_name),
        },
    )


def _content(
    package_name: str,
    *,
    description: str,
    latest_version: str | None,
    maintainer_count: int,
    modified_at: datetime | None,
    deprecated: str | None,
    repository_url: str | None,
) -> str:
    details = f"{package_name} has {maintainer_count} npm maintainer"
    details += "" if maintainer_count == 1 else "s"
    if latest_version:
        details += f" and latest version {latest_version}"
    if modified_at:
        details += f", last modified {modified_at.date().isoformat()}"
    details += "."
    if repository_url:
        details += f" Repository: {repository_url}."
    if deprecated:
        details += f" Deprecated: {deprecated}"
    if description and description != package_name:
        details += f" {description}"
    return details[:2000]


def _package_modified_time(payload: dict, *, latest_version: str | None) -> datetime | None:
    modified = _parse_datetime(_time_value(payload, "modified"))
    if modified is not None:
        return modified
    if latest_version:
        latest_time = _parse_datetime(_time_value(payload, latest_version))
        if latest_time is not None:
            return latest_time
    return _parse_datetime(_time_value(payload, "created"))


def _time_value(payload: dict, key: str) -> object:
    time_payload = payload.get("time")
    if not isinstance(time_payload, dict):
        return None
    return time_payload.get(key)


def _build_tags(package: str, *, keywords: list[str], deprecated: bool) -> list[str]:
    tags = ["javascript", "npm", "registry", "maintainer-activity", "package-health"]
    tags.extend(_package_parts(package))
    tags.extend(keywords)
    if deprecated:
        tags.append("deprecated")

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = tag.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _credibility(health: dict) -> float:
    score = 0.25
    score += min(int(health["maintainer_count"]), 5) * 0.08
    score += 0.15 if health["has_repository"] else 0
    score += 0.08 if health["has_license"] else 0
    score += 0.06 if health["has_homepage"] else 0
    score += min(math.log10(int(health["version_count"]) + 1) / 10, 0.12)
    if health["deprecated"]:
        score -= 0.15
    return min(max(round(score, 3), 0.05), 1.0)


def _package_api_url(package: str, *, base_url: str) -> str:
    return f"{base_url}/{quote(package, safe='@/')}"


def _search_api_url(*, base_url: str) -> str:
    return f"{base_url}/{NPM_SEARCH_PATH}"


def _package_url(package: str) -> str:
    return NPM_PACKAGE_URL.format(package=quote(package, safe="@/"))


def _signal_id(package: str) -> str:
    return f"npm-maintainer-activity:{package}"


def _repository_url(value: object) -> str | None:
    if isinstance(value, dict):
        return _string_or_none(value.get("url"))
    return _string_or_none(value)


def _people(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    people: list[dict[str, str]] = []
    for item in value:
        person = _person(item)
        if person:
            people.append(person)
    return people


def _person(value: object) -> dict[str, str] | None:
    if isinstance(value, dict):
        person = {
            key: text
            for key in ("name", "username", "email", "url")
            for text in [_string_or_none(value.get(key))]
            if text is not None
        }
        if "name" not in person and "username" in person:
            person["name"] = person["username"]
        return person or None
    if isinstance(value, str):
        text = value.strip()
        if text:
            return {"name": text}
    return None


def _first_person_name(people: list[dict[str, str]]) -> str | None:
    for person in people:
        name = _string_or_none(person.get("name") or person.get("username"))
        if name:
            return name
    return None


def _package_parts(package: str) -> list[str]:
    return [part for part in re.split(r"[/@._-]+", package.lower()) if part]


def _dedupe_terms(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_package_name(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


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


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


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
