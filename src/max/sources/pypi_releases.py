"""PyPI release history source adapter -- recent package release signals."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

PYPI_JSON_BASE_URL = "https://pypi.org/pypi"
PYPI_PROJECT_BASE_URL = "https://pypi.org/project"

_PRERELEASE_RE = re.compile(
    r"(?:^|[0-9.\-_])(?:a|alpha|b|beta|rc|pre|preview|dev)\d*(?:$|[.\-_+])",
    re.I,
)


class PyPIReleasesAdapter(SourceAdapter):
    """Fetch recent release metadata for configured PyPI packages."""

    @property
    def name(self) -> str:
        return "pypi_releases"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def packages(self) -> list[str]:
        return self._configured_terms("packages", [])

    @property
    def max_releases_per_package(self) -> int:
        return max(int(self._config.get("max_releases_per_package", 5)), 1)

    @property
    def include_prereleases(self) -> bool:
        return bool(self._config.get("include_prereleases", False))

    @property
    def base_url(self) -> str:
        return str(self._config.get("base_url", PYPI_JSON_BASE_URL)).rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_packages: set[str] = set()
        item_limit = max(limit, 0)
        if item_limit == 0:
            return signals

        async with httpx.AsyncClient(timeout=30) as client:
            for package in self.packages:
                if len(signals) >= item_limit:
                    break

                normalized = _normalize_package_name(package)
                if not normalized or normalized in seen_packages:
                    continue
                seen_packages.add(normalized)

                payload = await self._fetch_package_json(client, normalized)
                if payload is None:
                    continue

                for release in _recent_releases(
                    payload,
                    package=normalized,
                    max_releases=self.max_releases_per_package,
                    include_prereleases=self.include_prereleases,
                ):
                    if len(signals) >= item_limit:
                        break
                    signals.append(_release_to_signal(release, adapter_name=self.name))

        return signals[:item_limit]

    async def _fetch_package_json(
        self,
        client: httpx.AsyncClient,
        package: str,
    ) -> dict | None:
        url = _package_json_url(self.base_url, package)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-pypi-releases-adapter/0.1"},
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


def _recent_releases(
    payload: dict,
    *,
    package: str,
    max_releases: int,
    include_prereleases: bool,
) -> list[dict]:
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    releases = payload.get("releases") if isinstance(payload.get("releases"), dict) else {}
    if not releases:
        return []

    release_records: list[dict] = []
    for version, files in releases.items():
        version_text = str(version)
        if not include_prereleases and _is_prerelease(version_text):
            continue
        if not isinstance(files, list):
            continue

        upload_time = _latest_upload_time(files)
        if upload_time is None:
            continue

        release_records.append(
            {
                "package_name": str(info.get("name") or package),
                "normalized_package_name": package,
                "version": version_text,
                "upload_time": upload_time,
                "upload_time_raw": upload_time.isoformat(),
                "classifiers": _string_list(info.get("classifiers"))[:20],
                "project_urls": info.get("project_urls") if isinstance(info.get("project_urls"), dict) else {},
                "summary": str(info.get("summary") or ""),
                "description": str(info.get("description") or ""),
                "author": info.get("author") or info.get("author_email"),
                "requires_python": info.get("requires_python"),
                "package_url": info.get("package_url") or _package_project_url(package),
                "release_url": _release_project_url(package, version_text),
                "file_count": len(files),
                "yanked": any(bool(file.get("yanked")) for file in files if isinstance(file, dict)),
                "prerelease": _is_prerelease(version_text),
            }
        )

    release_records.sort(key=lambda item: item["upload_time"], reverse=True)
    return release_records[:max_releases]


def _release_to_signal(release: dict, *, adapter_name: str) -> Signal:
    package_name = release["package_name"]
    version = release["version"]
    title = f"{package_name}@{version}"
    content = _release_content(release)
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title,
        content=content,
        url=release["release_url"],
        author=release.get("author"),
        published_at=release["upload_time"],
        tags=_build_tags(release),
        credibility=_credibility(release),
        metadata={
            "signal_role": "adoption",
            "package_name": package_name,
            "pypi_name": package_name,
            "version": version,
            "release_url": release["release_url"],
            "upload_time": release["upload_time_raw"],
            "classifiers": release["classifiers"],
            "project_urls": release["project_urls"],
            "requires_python": release.get("requires_python"),
            "package_url": release["package_url"],
            "file_count": release["file_count"],
            "yanked": release["yanked"],
            "prerelease": release["prerelease"],
        },
    )


def _release_content(release: dict) -> str:
    summary = release["summary"].strip()
    description = release["description"].strip()
    parts = [
        f"{release['package_name']} released {release['version']} on PyPI.",
        summary,
        description[:1000],
    ]
    return "\n\n".join(part for part in parts if part)[:2000]


def _latest_upload_time(files: list[object]) -> datetime | None:
    dates = [
        parsed
        for file in files
        if isinstance(file, dict)
        for parsed in [_parse_datetime(file.get("upload_time_iso_8601") or file.get("upload_time"))]
        if parsed is not None
    ]
    if not dates:
        return None
    return max(dates)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _build_tags(release: dict) -> list[str]:
    tags = ["python", "pypi", "release", release["normalized_package_name"]]
    tags.extend(part for part in re.split(r"[-_.]+", release["normalized_package_name"]) if part)
    if release["prerelease"]:
        tags.append("prerelease")

    classifier_text = " ".join(release["classifiers"]).lower()
    if "artificial intelligence" in classifier_text:
        tags.append("ai")
    if "software development" in classifier_text:
        tags.append("devtools")
    if "security" in classifier_text:
        tags.append("security")

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        tag = str(tag).strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(release: dict) -> float:
    score = 0.45
    if release["classifiers"]:
        score += 0.1
    if release["project_urls"]:
        score += 0.1
    if release["file_count"] > 1:
        score += 0.05
    if release["yanked"]:
        score -= 0.2
    return min(max(round(score, 3), 0.1), 1.0)


def _package_json_url(base_url: str, package: str) -> str:
    return f"{base_url}/{quote(package)}/json"


def _package_project_url(package: str) -> str:
    return f"{PYPI_PROJECT_BASE_URL}/{quote(package)}/"


def _release_project_url(package: str, version: str) -> str:
    return f"{PYPI_PROJECT_BASE_URL}/{quote(package)}/{quote(version)}/"


def _normalize_package_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _is_prerelease(version: str) -> bool:
    return bool(_PRERELEASE_RE.search(version))
