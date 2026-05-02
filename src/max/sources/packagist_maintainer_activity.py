"""Packagist maintainer activity source adapter -- PHP package stewardship signals."""

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

PACKAGIST_BASE_URL = "https://packagist.org"


class PackagistMaintainerActivityAdapter(SourceAdapter):
    """Fetch Packagist package metadata as maintainer and release activity."""

    config_keys = ["packages", "package_names", "max_items", "max_results", "base_url", "timeout"]
    required_keys: list[str] = []
    description = (
        "Fetches Packagist package maintainer, author, release freshness, "
        "download, license, and repository metadata."
    )

    @property
    def name(self) -> str:
        return "packagist_maintainer_activity"

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
    def max_items(self) -> int:
        return _positive_int(self._config.get("max_items", self._config.get("max_results", 30)), 30)

    @property
    def base_url(self) -> str:
        configured = str(self._config.get("base_url", PACKAGIST_BASE_URL)).strip()
        return (configured or PACKAGIST_BASE_URL).rstrip("/")

    @property
    def timeout(self) -> float:
        value = self._config.get("timeout", 30)
        if isinstance(value, bool):
            return 30.0
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 30.0
        return parsed if parsed > 0 else 30.0

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = max(min(limit, self.max_items), 0)
        if item_limit == 0:
            return []

        signals: list[Signal] = []
        seen_signals: set[str] = set()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for package_name in self.packages:
                if len(signals) >= item_limit:
                    break

                payload = await self._fetch_package_metadata(client, package_name)
                if payload is None:
                    continue

                signal = _package_payload_to_signal(
                    payload,
                    requested_package=package_name,
                    adapter_name=self.name,
                    base_url=self.base_url,
                )
                if signal is None:
                    logger.warning("%s: malformed package metadata for %s", self.name, package_name)
                    continue
                if signal.id in seen_signals:
                    continue
                seen_signals.add(signal.id)
                signals.append(signal)

        return signals[:item_limit]

    async def _fetch_package_metadata(
        self,
        client: httpx.AsyncClient,
        package_name: str,
    ) -> dict | None:
        url = _api_url(package_name, base_url=self.base_url)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-packagist-maintainer-activity-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch package metadata for %s: %s", self.name, package_name, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, package_name, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse package metadata for %s: %s", self.name, package_name, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed package metadata for %s", self.name, package_name)
            return None
        return payload


def _package_payload_to_signal(
    payload: dict,
    *,
    requested_package: str,
    adapter_name: str,
    base_url: str,
) -> Signal | None:
    package = payload.get("package")
    if not isinstance(package, dict):
        return None

    package_name = _normalize_package_name(package.get("name")) or requested_package
    if not package_name:
        return None

    versions = _versions(package)
    latest = _latest_version(versions)
    latest_version = _string_or_none(latest.get("version")) if latest else None
    latest_release_at = _parse_datetime(latest.get("time")) if latest else _parse_datetime(package.get("time"))
    downloads = _download_count(package.get("downloads"), "total")
    monthly_downloads = _download_count(package.get("downloads"), "monthly")
    daily_downloads = _download_count(package.get("downloads"), "daily")
    maintainers = _maintainers(package.get("maintainers"))
    authors = _authors(latest.get("authors") if latest else None)
    people = _dedupe_people(maintainers + authors)
    if not people and latest_release_at is None and latest_version is None and downloads is None:
        return None

    licenses = _string_list(latest.get("license") if latest else package.get("license"))
    keywords = _string_list(latest.get("keywords") if latest else package.get("keywords"))
    repository_url = _string_or_none(package.get("repository")) or _repository_url(latest or {})
    package_url = _string_or_none(package.get("url")) or _package_url(package_name, base_url=base_url)
    api_url = _api_url(package_name, base_url=base_url)
    summary = _string_or_none(package.get("description")) or _string_or_none(latest.get("description") if latest else None) or package_name
    release_health = _release_health(versions)
    maintainer_count = len(maintainers) or len(people)
    health_indicators = {
        "maintainer_count": maintainer_count,
        "author_count": len(authors),
        "has_maintainers": bool(maintainers),
        "has_authors": bool(authors),
        "has_release_date": latest_release_at is not None,
        "has_repository": repository_url is not None,
        "has_license": bool(licenses),
        "downloads": downloads or 0,
        "release_count": release_health["total_releases_analyzed"],
        "abandoned": _is_abandoned(package),
    }
    release_age_days = (datetime.now(timezone.utc) - latest_release_at).days if latest_release_at else None

    return Signal(
        id=f"packagist-maintainer-activity:{package_name}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_name} Packagist maintainer activity",
        content=_content(
            package_name,
            summary=summary,
            latest_version=latest_version,
            maintainer_count=maintainer_count,
            released_at=latest_release_at,
            downloads=downloads,
            licenses=licenses,
            repository_url=repository_url,
        ),
        url=package_url,
        author=_first_person_name(people),
        published_at=latest_release_at,
        tags=_build_tags(package_name, licenses=licenses, keywords=keywords),
        credibility=_credibility(health_indicators),
        metadata={
            "signal_role": "market",
            "signal_kind": "maintainer_activity",
            "evidence_type": "package_health",
            "package_ecosystem": "packagist",
            "package_name": package_name,
            "packagist_name": package_name,
            "requested_package": requested_package,
            "version": latest_version,
            "latest_version": latest_version,
            "maintainers": maintainers,
            "authors": authors,
            "people": people,
            "maintainer_count": maintainer_count,
            "author_count": len(authors),
            "downloads": downloads,
            "download_count": downloads,
            "monthly_downloads": monthly_downloads,
            "daily_downloads": daily_downloads,
            "licenses": licenses,
            "license": licenses,
            "keywords": keywords,
            "latest_release_at": latest_release_at.isoformat() if latest_release_at else None,
            "released_at": latest_release_at.isoformat() if latest_release_at else None,
            "latest_release_age_days": release_age_days,
            "release_age_days": release_age_days,
            "release_health": release_health,
            "repository_url": repository_url,
            "homepage": _string_or_none(latest.get("homepage") if latest else package.get("homepage")),
            "type": _string_or_none(latest.get("type") if latest else package.get("type")),
            "summary": summary,
            "abandoned": package.get("abandoned"),
            "api_url": api_url,
            "source_url": package_url,
            "package_url": package_url,
            "health_indicators": health_indicators,
        },
    )


def _content(
    package_name: str,
    *,
    summary: str,
    latest_version: str | None,
    maintainer_count: int,
    released_at: datetime | None,
    downloads: int | None,
    licenses: list[str],
    repository_url: str | None,
) -> str:
    details = f"{package_name} has {maintainer_count} Packagist maintainer"
    details += "" if maintainer_count == 1 else "s"
    if latest_version:
        details += f" and latest version {latest_version}"
    if released_at:
        details += f", released {released_at.date().isoformat()}"
    else:
        details += ", with no dated release in the Packagist response"
    details += "."
    if downloads is not None:
        details += f" Total downloads: {downloads:,}."
    if licenses:
        details += f" Licenses: {', '.join(licenses[:5])}."
    if repository_url:
        details += " Repository metadata is present."
    if summary and summary != package_name:
        details += f" {summary}"
    return details[:2000]


def _versions(package: dict) -> list[dict]:
    versions = package.get("versions")
    if isinstance(versions, dict):
        return [version for version in versions.values() if isinstance(version, dict)]
    if isinstance(versions, list):
        return [version for version in versions if isinstance(version, dict)]
    return []


def _latest_version(versions: list[dict]) -> dict | None:
    candidates = [
        version
        for version in versions
        if _string_or_none(version.get("version")) is not None
        and not str(version.get("version")).lower().startswith("dev-")
    ]
    if not candidates:
        candidates = list(versions)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda version: (
            _parse_datetime(version.get("time")) or datetime.min.replace(tzinfo=timezone.utc),
            str(version.get("version_normalized") or version.get("version") or ""),
        ),
    )


def _release_health(versions: list[dict]) -> dict:
    records: list[dict[str, object]] = []
    for version in versions:
        version_name = _string_or_none(version.get("version"))
        released_at = _parse_datetime(version.get("time"))
        if version_name is None or released_at is None:
            continue
        if version_name.lower().startswith("dev-"):
            continue
        records.append(
            {
                "version": version_name,
                "released_at": released_at,
                "released_at_raw": released_at.isoformat(),
            }
        )

    records.sort(key=lambda item: item["released_at"], reverse=True)
    recent = records[:10]
    dated = [record["released_at"] for record in recent if isinstance(record["released_at"], datetime)]
    latest = dated[0] if dated else None
    oldest = dated[-1] if dated else None

    return {
        "latest_release_at": latest.isoformat() if latest else None,
        "oldest_release_at": oldest.isoformat() if oldest else None,
        "total_releases_analyzed": len(recent),
        "releases_with_dates": len(dated),
        "average_days_between_releases": _average_days_between(dated),
        "recent_releases": [
            {
                "version": str(record["version"]),
                "released_at": str(record["released_at_raw"]),
            }
            for record in recent
        ],
    }


def _average_days_between(dates: list[datetime]) -> float | None:
    if len(dates) < 2:
        return None
    intervals = [
        abs((newer - older).total_seconds()) / 86_400
        for newer, older in zip(dates, dates[1:])
    ]
    return round(sum(intervals) / len(intervals), 1)


def _maintainers(payload: object) -> list[dict[str, str]]:
    if not isinstance(payload, list):
        return []
    people: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        person = {"role": "maintainer"}
        for key in ("name", "email", "avatar"):
            value = _string_or_none(item.get(key))
            if value:
                person[key] = value
        if len(person) > 1:
            people.append(person)
    return _dedupe_people(people)


def _authors(payload: object) -> list[dict[str, str]]:
    if not isinstance(payload, list):
        return []
    people: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        person = {"role": "author"}
        for key in ("name", "email", "homepage"):
            value = _string_or_none(item.get(key))
            if value:
                person[key] = value
        if len(person) > 1:
            people.append(person)
    return _dedupe_people(people)


def _dedupe_people(people: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for person in people:
        identity = (
            person.get("role", "").lower(),
            person.get("name", "").lower(),
            person.get("email", "").lower(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(person)
    return deduped


def _first_person_name(people: list[dict[str, str]]) -> str | None:
    for person in people:
        name = _string_or_none(person.get("name"))
        if name:
            return name
    return None


def _build_tags(package_name: str, *, licenses: list[str], keywords: list[str]) -> list[str]:
    tags = ["php", "packagist", "registry", "maintainer-activity", "package-health"]
    tags.extend(part for part in re.split(r"[/._-]+", package_name.lower()) if part)
    tags.extend(keyword.lower() for keyword in keywords)
    tags.extend(license_name.lower() for license_name in licenses)
    return _dedupe_tags(tags)


def _credibility(health: dict) -> float:
    score = 0.2
    score += min(int(health["maintainer_count"]), 5) * 0.08
    score += 0.15 if health["has_release_date"] else 0
    score += 0.1 if health["has_repository"] else 0
    score += 0.08 if health["has_license"] else 0
    score += min(math.log10(int(health["downloads"]) + 1) / 10, 0.14)
    score += min(math.log10(int(health["release_count"]) + 1) / 8, 0.08)
    if health["abandoned"]:
        score -= 0.2
    return min(max(round(score, 3), 0.05), 1.0)


def _repository_url(version: dict) -> str | None:
    source = version.get("source") if isinstance(version.get("source"), dict) else {}
    support = version.get("support") if isinstance(version.get("support"), dict) else {}
    return _string_or_none(source.get("url")) or _string_or_none(support.get("source"))


def _is_abandoned(package: dict) -> bool:
    abandoned = package.get("abandoned")
    return bool(abandoned) and not isinstance(abandoned, str)


def _api_url(package_name: str, *, base_url: str) -> str:
    return f"{base_url}/packages/{quote(package_name, safe='/')}.json"


def _package_url(package_name: str, *, base_url: str) -> str:
    return f"{base_url}/packages/{quote(package_name, safe='/')}"


def _normalize_package_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


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


def _download_count(value: object, key: str) -> int | None:
    if not isinstance(value, dict):
        return None
    return _int_or_none(value.get(key))


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


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,;]", value) if part.strip()]
    return []


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


def _dedupe_tags(tags: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = str(tag).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]
