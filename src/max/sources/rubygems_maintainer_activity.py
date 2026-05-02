"""RubyGems maintainer activity source adapter -- package stewardship signals."""

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

RUBYGEMS_API_URL = "https://rubygems.org/api/v1"
RUBYGEMS_PACKAGE_PAGE = "https://rubygems.org/gems/{gem_name}"


class RubyGemsMaintainerActivityAdapter(SourceAdapter):
    """Fetch RubyGems package metadata as maintainer and release activity."""

    config_keys = ["gems", "packages", "package_names", "max_items", "max_results", "rubygems_api_url", "timeout"]
    required_keys: list[str] = []
    description = (
        "Fetches RubyGems package author, owner, release freshness, license, "
        "download, and project link metadata."
    )

    @property
    def name(self) -> str:
        return "rubygems_maintainer_activity"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def gems(self) -> list[str]:
        return _dedupe_terms(
            self._configured_terms("gems", [])
            + self._configured_terms("packages", [])
            + self._configured_terms("package_names", [])
        )

    @property
    def max_items(self) -> int:
        return _positive_int(self._config.get("max_items", self._config.get("max_results", 30)), 30)

    @property
    def rubygems_api_url(self) -> str:
        configured = str(self._config.get("rubygems_api_url", RUBYGEMS_API_URL)).strip()
        return (configured or RUBYGEMS_API_URL).rstrip("/")

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
            for gem_name in self.gems:
                if len(signals) >= item_limit:
                    break

                payload = await self._fetch_gem_metadata(client, gem_name)
                if payload is None:
                    continue
                if not _has_minimal_activity_payload(payload, requested_gem=gem_name):
                    logger.warning("%s: malformed gem metadata for %s", self.name, gem_name)
                    continue

                owners = await self._fetch_gem_owners(client, gem_name)
                signal = _gem_payload_to_signal(
                    payload,
                    requested_gem=gem_name,
                    owners=owners,
                    adapter_name=self.name,
                    api_url=_gem_api_url(self.rubygems_api_url, gem_name),
                )
                if signal is None:
                    logger.warning("%s: malformed gem metadata for %s", self.name, gem_name)
                    continue
                if signal.id in seen_signals:
                    continue
                seen_signals.add(signal.id)
                signals.append(signal)

        return signals[:item_limit]

    async def _fetch_gem_metadata(
        self,
        client: httpx.AsyncClient,
        gem_name: str,
    ) -> dict | None:
        url = _gem_api_url(self.rubygems_api_url, gem_name)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-rubygems-maintainer-activity-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch gem metadata for %s: %s", self.name, gem_name, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, gem_name, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse gem metadata for %s: %s", self.name, gem_name, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed gem metadata for %s", self.name, gem_name)
            return None
        return payload

    async def _fetch_gem_owners(
        self,
        client: httpx.AsyncClient,
        gem_name: str,
    ) -> list[dict[str, str]]:
        url = _owners_api_url(self.rubygems_api_url, gem_name)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-rubygems-maintainer-activity-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch owners for %s: %s", self.name, gem_name, e)
            return []
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: owner request failed for %s: %s", self.name, gem_name, e)
            return []
        except ValueError as e:
            logger.warning("%s: failed to parse owners for %s: %s", self.name, gem_name, e)
            return []

        return _owners(payload)


def _gem_payload_to_signal(
    payload: dict,
    *,
    requested_gem: str,
    owners: list[dict[str, str]],
    adapter_name: str,
    api_url: str,
) -> Signal | None:
    gem_name = _string_or_none(payload.get("name")) or requested_gem
    normalized_name = _normalize_gem_name(gem_name)
    if not normalized_name:
        return None

    latest_version = _string_or_none(payload.get("version"))
    released_at = _parse_datetime(payload.get("version_created_at"))
    downloads = _int_or_none(payload.get("downloads"))
    if latest_version is None and released_at is None and downloads is None:
        return None

    authors = _string_list(payload.get("authors"))
    licenses = _string_list(payload.get("licenses"))
    project_uri = _string_or_none(payload.get("project_uri")) or _package_url(normalized_name)
    project_links = _project_links(payload, fallback_project_uri=project_uri)
    summary = _string_or_none(payload.get("info")) or gem_name
    release_age_days = (datetime.now(timezone.utc) - released_at).days if released_at else None
    version_downloads = _int_or_none(payload.get("version_downloads"))
    owner_count = len(owners)
    maintainer_count = owner_count or len(authors)
    health_indicators = {
        "maintainer_count": maintainer_count,
        "owner_count": owner_count,
        "author_count": len(authors),
        "has_release_date": released_at is not None,
        "has_project_links": bool(project_links),
        "has_license": bool(licenses),
        "has_source_code": project_links.get("source_code") is not None,
        "downloads": downloads or 0,
    }

    return Signal(
        id=f"rubygems-maintainer-activity:{normalized_name}",
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{normalized_name} RubyGems maintainer activity",
        content=_content(
            normalized_name,
            summary=summary,
            latest_version=latest_version,
            maintainers=maintainer_count,
            released_at=released_at,
            downloads=downloads,
            licenses=licenses,
            project_links=project_links,
        ),
        url=project_uri,
        author=authors[0] if authors else _first_owner_name(owners),
        published_at=released_at,
        tags=_build_tags(normalized_name, licenses=licenses),
        credibility=_credibility(health_indicators),
        metadata={
            "signal_role": "market",
            "signal_kind": "maintainer_activity",
            "evidence_type": "package_health",
            "package_ecosystem": "rubygems",
            "package_name": normalized_name,
            "gem_name": normalized_name,
            "requested_gem": requested_gem,
            "version": latest_version,
            "latest_version": latest_version,
            "authors": authors,
            "maintainers": owners,
            "owners": owners,
            "maintainer_count": maintainer_count,
            "owner_count": owner_count,
            "downloads": downloads,
            "download_count": downloads,
            "version_downloads": version_downloads,
            "licenses": licenses,
            "latest_release_at": released_at.isoformat() if released_at else None,
            "version_created_at": released_at.isoformat() if released_at else None,
            "latest_release_age_days": release_age_days,
            "release_age_days": release_age_days,
            "summary": summary,
            "project_links": project_links,
            "project_uri": project_uri,
            "gem_uri": _string_or_none(payload.get("gem_uri")),
            "homepage_uri": project_links.get("homepage"),
            "source_code_uri": project_links.get("source_code"),
            "documentation_uri": project_links.get("documentation"),
            "bug_tracker_uri": project_links.get("bug_tracker"),
            "changelog_uri": project_links.get("changelog"),
            "wiki_uri": project_links.get("wiki"),
            "mailing_list_uri": project_links.get("mailing_list"),
            "api_url": api_url,
            "source_url": project_uri,
            "health_indicators": health_indicators,
        },
    )


def _has_minimal_activity_payload(payload: dict, *, requested_gem: str) -> bool:
    gem_name = _string_or_none(payload.get("name")) or requested_gem
    if not _normalize_gem_name(gem_name):
        return False
    return (
        _string_or_none(payload.get("version")) is not None
        or _parse_datetime(payload.get("version_created_at")) is not None
        or _int_or_none(payload.get("downloads")) is not None
    )


def _content(
    gem_name: str,
    *,
    summary: str,
    latest_version: str | None,
    maintainers: int,
    released_at: datetime | None,
    downloads: int | None,
    licenses: list[str],
    project_links: dict[str, str],
) -> str:
    details = f"{gem_name} has {maintainers} RubyGems maintainer"
    details += "" if maintainers == 1 else "s"
    if latest_version:
        details += f" and latest version {latest_version}"
    if released_at:
        details += f", released {released_at.date().isoformat()}"
    details += "."
    if downloads is not None:
        details += f" Total downloads: {downloads:,}."
    if licenses:
        details += f" Licenses: {', '.join(licenses[:5])}."
    if project_links:
        details += f" Project links: {', '.join(sorted(project_links)[:6])}."
    if summary and summary != gem_name:
        details += f" {summary}"
    return details[:2000]


def _project_links(payload: dict, *, fallback_project_uri: str) -> dict[str, str]:
    fields = {
        "project": fallback_project_uri,
        "homepage": _string_or_none(payload.get("homepage_uri")),
        "source_code": _string_or_none(payload.get("source_code_uri")),
        "documentation": _string_or_none(payload.get("documentation_uri")),
        "bug_tracker": _string_or_none(payload.get("bug_tracker_uri")),
        "changelog": _string_or_none(payload.get("changelog_uri")),
        "wiki": _string_or_none(payload.get("wiki_uri")),
        "mailing_list": _string_or_none(payload.get("mailing_list_uri")),
    }
    return {key: value for key, value in fields.items() if value}


def _owners(payload: object) -> list[dict[str, str]]:
    if not isinstance(payload, list):
        return []

    owners: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        owner = {
            key: text
            for key in ("handle", "email", "id")
            for text in [_string_or_none(item.get(key))]
            if text is not None
        }
        name = _string_or_none(item.get("handle") or item.get("name"))
        if name:
            owner["name"] = name
        if not owner:
            continue
        identity = (owner.get("handle", owner.get("name", "")).lower(), owner.get("email", "").lower())
        if identity in seen:
            continue
        seen.add(identity)
        owners.append(owner)
    return owners


def _first_owner_name(owners: list[dict[str, str]]) -> str | None:
    for owner in owners:
        name = _string_or_none(owner.get("name") or owner.get("handle"))
        if name:
            return name
    return None


def _build_tags(gem_name: str, *, licenses: list[str]) -> list[str]:
    tags = ["ruby", "rubygems", "registry", "maintainer-activity", "package-health"]
    tags.extend(part for part in re.split(r"[-_.]+", gem_name.lower()) if part)
    tags.extend(license_name.lower() for license_name in licenses)

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
    score += min(int(health["maintainer_count"]), 5) * 0.08
    score += 0.15 if health["has_release_date"] else 0
    score += 0.1 if health["has_project_links"] else 0
    score += 0.08 if health["has_license"] else 0
    score += 0.07 if health["has_source_code"] else 0
    score += min(math.log10(int(health["downloads"]) + 1) / 10, 0.14)
    return min(max(round(score, 3), 0.05), 1.0)


def _gem_api_url(base_url: str, gem_name: str) -> str:
    return f"{base_url}/gems/{quote(gem_name, safe='')}.json"


def _owners_api_url(base_url: str, gem_name: str) -> str:
    return f"{base_url}/gems/{quote(gem_name, safe='')}/owners.json"


def _package_url(gem_name: str) -> str:
    return RUBYGEMS_PACKAGE_PAGE.format(gem_name=quote(gem_name, safe=""))


def _normalize_gem_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _dedupe_terms(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_gem_name(value)
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
