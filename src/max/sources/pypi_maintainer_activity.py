"""PyPI maintainer activity source adapter -- package stewardship signals."""

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

PYPI_API_URL = "https://pypi.org/pypi"
PYPI_PROJECT_URL = "https://pypi.org/project"


class PyPIMaintainerActivityAdapter(SourceAdapter):
    """Fetch PyPI package metadata as maintainer activity and release health."""

    @property
    def name(self) -> str:
        return "pypi_maintainer_activity"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def packages(self) -> list[str]:
        return _dedupe_terms(self._configured_terms("packages", []))

    @property
    def pypi_api_url(self) -> str:
        configured = str(self._config.get("pypi_api_url", PYPI_API_URL)).strip()
        return (configured or PYPI_API_URL).rstrip("/")

    @property
    def max_releases(self) -> int:
        return _positive_int(self._config.get("max_releases"), default=10)

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
        signals: list[Signal] = []
        item_limit = max(limit, 0)
        if item_limit == 0:
            return signals

        seen_signals: set[str] = set()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for package in self.packages:
                if len(signals) >= item_limit:
                    break

                payload = await self._fetch_package_json(client, package)
                if payload is None:
                    continue

                signal = _package_payload_to_signal(
                    payload,
                    requested_package=package,
                    adapter_name=self.name,
                    api_url=_package_api_url(self.pypi_api_url, package),
                    max_releases=self.max_releases,
                )
                if signal is None:
                    logger.warning("%s: malformed package metadata for %s", self.name, package)
                    continue
                if signal.id in seen_signals:
                    continue
                seen_signals.add(signal.id)
                signals.append(signal)

        return signals[:item_limit]

    async def _fetch_package_json(
        self,
        client: httpx.AsyncClient,
        package: str,
    ) -> dict | None:
        url = _package_api_url(self.pypi_api_url, package)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-pypi-maintainer-activity-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch package metadata for %s: %s", self.name, package, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, package, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse package metadata for %s: %s", self.name, package, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed package metadata for %s", self.name, package)
            return None
        return payload


def _package_payload_to_signal(
    payload: dict,
    *,
    requested_package: str,
    adapter_name: str,
    api_url: str,
    max_releases: int,
) -> Signal | None:
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    package_name = _string_or_none(info.get("name")) or requested_package
    normalized_package = _normalize_package_name(package_name)
    if not normalized_package:
        return None

    releases = payload.get("releases") if isinstance(payload.get("releases"), dict) else {}
    release_health = _release_health(releases, max_releases=max_releases)
    maintainers = _people(
        [
            ("maintainer", info.get("maintainer"), info.get("maintainer_email")),
            ("author", info.get("author"), info.get("author_email")),
        ]
    )
    classifiers = _string_list(info.get("classifiers"))[:20]
    project_urls = info.get("project_urls") if isinstance(info.get("project_urls"), dict) else {}
    package_url = _string_or_none(info.get("package_url")) or _package_project_url(normalized_package)
    latest_version = _string_or_none(info.get("version"))
    summary = _string_or_none(info.get("summary")) or package_name

    health_indicators = {
        "maintainer_count": len(maintainers),
        "has_maintainers": bool(maintainers),
        "has_release_data": release_health["latest_release_at"] is not None,
        "has_project_urls": bool(project_urls),
        "has_classifiers": bool(classifiers),
        "has_license": _string_or_none(info.get("license")) is not None,
        "release_count": release_health["total_releases_analyzed"],
    }

    latest_release_at = _parse_datetime(release_health["latest_release_at"])
    return Signal(
        id=f"pypi-maintainer-activity:{normalized_package}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_name} PyPI maintainer activity",
        content=_content(
            package_name,
            summary=summary,
            latest_version=latest_version,
            maintainers=maintainers,
            release_health=release_health,
            project_urls=project_urls,
        ),
        url=package_url,
        author=_first_person_name(maintainers),
        published_at=latest_release_at,
        tags=_build_tags(normalized_package, classifiers=classifiers),
        credibility=_credibility(health_indicators),
        metadata={
            "signal_role": "market",
            "signal_kind": "maintainer_activity",
            "evidence_type": "package_health",
            "package_ecosystem": "pypi",
            "package_name": package_name,
            "pypi_name": package_name,
            "requested_package": requested_package,
            "latest_version": latest_version,
            "maintainers": maintainers,
            "maintainer_count": len(maintainers),
            "author": _string_or_none(info.get("author")),
            "author_email": _string_or_none(info.get("author_email")),
            "maintainer": _string_or_none(info.get("maintainer")),
            "maintainer_email": _string_or_none(info.get("maintainer_email")),
            "classifiers": classifiers,
            "project_urls": project_urls,
            "requires_python": _string_or_none(info.get("requires_python")),
            "license": _string_or_none(info.get("license")),
            "summary": summary,
            "package_url": package_url,
            "api_url": api_url,
            "source_url": package_url,
            "release_health": release_health,
            "health_indicators": health_indicators,
        },
    )


def _release_health(releases: dict, *, max_releases: int) -> dict:
    records: list[dict[str, object]] = []
    for version, files in releases.items():
        if not isinstance(files, list):
            continue
        upload_time = _latest_upload_time(files)
        if upload_time is None:
            continue
        records.append(
            {
                "version": str(version),
                "upload_time": upload_time,
                "upload_time_raw": upload_time.isoformat(),
                "file_count": len(files),
                "yanked": any(bool(file.get("yanked")) for file in files if isinstance(file, dict)),
            }
        )

    records.sort(key=lambda item: item["upload_time"], reverse=True)
    recent = records[:max_releases]
    dated = [record["upload_time"] for record in recent if isinstance(record["upload_time"], datetime)]
    latest = dated[0] if dated else None
    oldest = dated[-1] if dated else None
    age_days = (datetime.now(timezone.utc) - latest).days if latest else None

    return {
        "latest_release_at": latest.isoformat() if latest else None,
        "latest_release_age_days": age_days,
        "oldest_release_at": oldest.isoformat() if oldest else None,
        "total_releases_analyzed": len(recent),
        "releases_with_dates": len(dated),
        "average_days_between_releases": _average_days_between(dated),
        "recent_releases": [
            {
                "version": str(record["version"]),
                "upload_time": str(record["upload_time_raw"]),
                "file_count": int(record["file_count"]),
                "yanked": bool(record["yanked"]),
            }
            for record in recent
        ],
    }


def _content(
    package_name: str,
    *,
    summary: str,
    latest_version: str | None,
    maintainers: list[dict[str, str]],
    release_health: dict,
    project_urls: dict,
) -> str:
    maintainer_count = len(maintainers)
    details = f"{package_name} has {maintainer_count} PyPI maintainer"
    details += "" if maintainer_count == 1 else "s"
    if latest_version:
        details += f" and latest version {latest_version}"
    if release_health["latest_release_at"]:
        details += f", last released {_parse_datetime(release_health['latest_release_at']).date().isoformat()}"
    else:
        details += ", with no dated releases in the PyPI response"
    details += "."
    if release_health["average_days_between_releases"] is not None:
        details += f" Recent release cadence averages {release_health['average_days_between_releases']} days."
    if project_urls:
        details += f" Project URLs: {', '.join(sorted(str(key) for key in project_urls)[:5])}."
    if summary and summary != package_name:
        details += f" {summary}"
    return details[:2000]


def _latest_upload_time(files: list[object]) -> datetime | None:
    dates = [
        parsed
        for file in files
        if isinstance(file, dict)
        for parsed in [_parse_datetime(file.get("upload_time_iso_8601") or file.get("upload_time"))]
        if parsed is not None
    ]
    return max(dates) if dates else None


def _average_days_between(dates: list[datetime]) -> float | None:
    if len(dates) < 2:
        return None
    intervals = [
        abs((newer - older).total_seconds()) / 86_400
        for newer, older in zip(dates, dates[1:])
    ]
    return round(sum(intervals) / len(intervals), 1)


def _people(rows: list[tuple[str, object, object]]) -> list[dict[str, str]]:
    people: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for role, name_value, email_value in rows:
        name = _string_or_none(name_value)
        email = _string_or_none(email_value)
        if not name and not email:
            continue
        person = {"role": role}
        if name:
            person["name"] = name
        if email:
            person["email"] = email
        identity = (person.get("name", "").lower(), person.get("email", "").lower())
        if identity in seen:
            continue
        seen.add(identity)
        people.append(person)
    return people


def _first_person_name(people: list[dict[str, str]]) -> str | None:
    for person in people:
        name = _string_or_none(person.get("name"))
        if name:
            return name
    return None


def _build_tags(package: str, *, classifiers: list[str]) -> list[str]:
    tags = ["python", "pypi", "registry", "maintainer-activity", "package-health"]
    tags.extend(part for part in re.split(r"[-_.]+", package) if part)
    classifier_text = " ".join(classifiers).lower()
    if "artificial intelligence" in classifier_text:
        tags.append("ai")
    if "software development" in classifier_text:
        tags.append("devtools")
    if "security" in classifier_text:
        tags.append("security")

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = str(tag).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _credibility(health: dict) -> float:
    score = 0.2
    score += min(int(health["maintainer_count"]), 4) * 0.08
    score += 0.2 if health["has_release_data"] else 0
    score += 0.1 if health["has_project_urls"] else 0
    score += 0.08 if health["has_classifiers"] else 0
    score += 0.07 if health["has_license"] else 0
    score += min(math.log10(int(health["release_count"]) + 1) / 8, 0.12)
    return min(max(round(score, 3), 0.05), 1.0)


def _package_api_url(base_url: str, package: str) -> str:
    return f"{base_url}/{quote(package)}/json"


def _package_project_url(package: str) -> str:
    return f"{PYPI_PROJECT_URL}/{quote(package)}/"


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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)
