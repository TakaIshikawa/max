"""Hex.pm source adapter - BEAM ecosystem package metadata and adoption signals."""

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

HEXPM_API_BASE_URL = "https://hex.pm/api"
HEXPM_PACKAGE_URL = "https://hex.pm/packages/{package}"


class HexPmAdapter(SourceAdapter):
    """Fetch configured Hex.pm package metadata and download adoption signals."""

    @property
    def name(self) -> str:
        return "hexpm"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def packages(self) -> list[str]:
        return self._configured_terms("packages", [])

    @property
    def max_results(self) -> int:
        return max(int(self._config.get("max_results", 30)), 1)

    @property
    def api_base_url(self) -> str:
        return str(self._config.get("api_base_url", HEXPM_API_BASE_URL)).rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_packages: set[str] = set()
        item_limit = max(min(limit, self.max_results), 0)
        if item_limit == 0 or not self.packages:
            return signals

        async with httpx.AsyncClient(timeout=30) as client:
            for package in self.packages:
                if len(signals) >= item_limit:
                    break

                normalized = _normalize_package_name(package)
                if not normalized or normalized in seen_packages:
                    continue
                seen_packages.add(normalized)

                payload = await self._fetch_package(client, normalized)
                if payload is None:
                    continue

                signal = _package_to_signal(
                    payload,
                    fallback_name=normalized,
                    adapter_name=self.name,
                    api_base_url=self.api_base_url,
                )
                if signal is None:
                    logger.warning("%s: malformed package record for %s", self.name, normalized)
                    continue

                signals.append(signal)

        return signals[:item_limit]

    async def _fetch_package(
        self,
        client: httpx.AsyncClient,
        package: str,
    ) -> dict | None:
        url = _package_api_url(self.api_base_url, package)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-hexpm-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Hex.pm package %s: %s", self.name, package, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for Hex.pm package %s: %s", self.name, package, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse Hex.pm package %s: %s", self.name, package, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed package record for %s", self.name, package)
            return None
        return payload


def _package_to_signal(
    package: dict,
    *,
    fallback_name: str,
    adapter_name: str,
    api_base_url: str,
) -> Signal | None:
    package_name = _normalize_package_name(package.get("name")) or fallback_name
    if not package_name:
        return None

    meta = package.get("meta") if isinstance(package.get("meta"), dict) else {}
    downloads = _downloads(package.get("downloads"))
    total_downloads = downloads.get("all", 0)
    recent_downloads = downloads.get("recent", 0)
    latest_version = _string_or_none(package.get("latest_version"))
    latest_stable_version = _string_or_none(package.get("latest_stable_version"))
    version = latest_stable_version or latest_version or ""
    updated_at = _parse_datetime(package.get("updated_at"))
    description = (
        _string_or_none(meta.get("description"))
        or _string_or_none(package.get("description"))
        or package_name
    )
    links = _links(meta.get("links"))
    package_url = _package_page_url(package_name)
    repository_url = _repository_url(links)
    licenses = _string_list(meta.get("licenses"))

    metadata = {
        "signal_role": "market",
        "signal_kind": "package_metadata",
        "package_ecosystem": "hexpm",
        "package_name": package_name,
        "hexpm_name": package_name,
        "latest_version": latest_version,
        "latest_stable_version": latest_stable_version,
        "version": version,
        "downloads": total_downloads,
        "download_count": total_downloads,
        "recent_downloads": recent_downloads,
        "daily_downloads": downloads.get("day", 0),
        "weekly_downloads": downloads.get("week", 0),
        "description": description,
        "links": links,
        "repository_url": repository_url,
        "licenses": licenses,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "package_url": package_url,
        "api_url": _package_api_url(api_base_url, package_name),
    }

    return Signal(
        id=_signal_id(package_name, version),
        source_type=SignalSourceType.REGISTRY,
        source_adapter=adapter_name,
        title=f"{package_name}@{version}" if version else package_name,
        content=_content(package_name, description, total_downloads, recent_downloads),
        url=repository_url or package_url,
        published_at=updated_at,
        tags=_build_tags(package_name, licenses=licenses, has_repository=repository_url is not None),
        credibility=_credibility(total_downloads=total_downloads, recent_downloads=recent_downloads),
        metadata=metadata,
    )


def _package_api_url(api_base_url: str, package: str) -> str:
    return f"{api_base_url}/packages/{quote(package, safe='')}"


def _package_page_url(package: str) -> str:
    return HEXPM_PACKAGE_URL.format(package=quote(package, safe=""))


def _signal_id(package_name: str, version: str) -> str:
    normalized_version = version.strip().lower() or "unknown"
    return f"hexpm:{package_name}:{normalized_version}"


def _content(
    package_name: str,
    description: str,
    total_downloads: int,
    recent_downloads: int,
) -> str:
    if total_downloads or recent_downloads:
        return (
            f"{description[:400]} "
            f"Hex.pm reports {total_downloads:,} total downloads and "
            f"{recent_downloads:,} recent downloads for {package_name}."
        )
    return description[:500]


def _downloads(value: object) -> dict[str, int]:
    if isinstance(value, dict):
        return {
            "all": _int_or_zero(value.get("all")),
            "recent": _int_or_zero(value.get("recent")),
            "day": _int_or_zero(value.get("day")),
            "week": _int_or_zero(value.get("week")),
        }
    return {
        "all": _int_or_zero(value),
        "recent": 0,
        "day": 0,
        "week": 0,
    }


def _links(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    links: dict[str, str] = {}
    for key, url in value.items():
        normalized_key = _string_or_none(key)
        normalized_url = _string_or_none(url)
        if normalized_key is None or normalized_url is None:
            continue
        links[normalized_key] = normalized_url
    return links


def _repository_url(links: dict[str, str]) -> str | None:
    preferred_keys = ("GitHub", "GitLab", "Repository", "Source", "Code")
    for key in preferred_keys:
        url = links.get(key)
        if url:
            return url

    for key, url in links.items():
        lowered = key.lower()
        if any(term in lowered for term in ("github", "gitlab", "repo", "source", "code")):
            return url
    return None


def _build_tags(package_name: str, *, licenses: list[str], has_repository: bool) -> list[str]:
    tags = ["elixir", "erlang", "beam", "hexpm", "package", "downloads"]
    tags.extend(licenses)
    tags.extend(part for part in re.split(r"[-_.]+", package_name.lower()) if part)
    if has_repository:
        tags.append("open-source")

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = tag.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:10]


def _credibility(*, total_downloads: int, recent_downloads: int) -> float:
    total_score = min(math.log10(total_downloads + 1) / 8, 0.55)
    recent_score = min(math.log10(recent_downloads + 1) / 7, 0.2)
    return min(round(0.15 + total_score + recent_score, 3), 1.0)


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


def _normalize_package_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _int_or_zero(value: object) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.replace(",", " ").split() if part.strip()]
    return []
