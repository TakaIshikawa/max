"""RubyGems download trend source adapter — gem popularity signals."""

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

RUBYGEMS_DETAILS_API = "https://rubygems.org/api/v1/gems/{gem_name}.json"
RUBYGEMS_PACKAGE_PAGE = "https://rubygems.org/gems/{gem_name}"


class RubyGemsDownloadTrendsAdapter(SourceAdapter):
    """Fetch RubyGems download totals for configured gems."""

    @property
    def name(self) -> str:
        return "rubygems_download_trends"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def packages(self) -> list[str]:
        return self._configured_terms("packages", [])

    @property
    def max_items(self) -> int:
        return max(int(self._config.get("max_items", self._config.get("max_results", 30))), 1)

    @property
    def min_downloads(self) -> int:
        return max(int(self._config.get("min_downloads", 0)), 0)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_gems: set[str] = set()
        item_limit = max(min(limit, self.max_items), 0)
        if item_limit == 0:
            return signals

        async with httpx.AsyncClient(timeout=30) as client:
            for package in self.packages:
                if len(signals) >= item_limit:
                    break

                normalized = _normalize_gem_name(package)
                if not normalized or normalized in seen_gems:
                    continue
                seen_gems.add(normalized)

                gem = await self._fetch_gem_details(client, normalized)
                if gem is None:
                    continue

                signal = _gem_downloads_to_signal(gem, fallback_name=normalized, adapter_name=self.name)
                if signal is None:
                    logger.warning("%s: malformed download stats for %s", self.name, normalized)
                    continue
                if signal.metadata["downloads"] < self.min_downloads:
                    continue

                signals.append(signal)

        return signals[:item_limit]

    async def _fetch_gem_details(
        self,
        client: httpx.AsyncClient,
        gem_name: str,
    ) -> dict | None:
        url = _api_url(gem_name)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-rubygems-download-trends-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch download stats for %s: %s", self.name, gem_name, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, gem_name, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse download stats for %s: %s", self.name, gem_name, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed download stats for %s", self.name, gem_name)
            return None
        return payload


def _gem_downloads_to_signal(
    gem: dict,
    *,
    fallback_name: str,
    adapter_name: str,
) -> Signal | None:
    gem_name = _string_or_none(gem.get("name")) or fallback_name
    normalized_name = _normalize_gem_name(gem_name)
    if not normalized_name:
        return None

    downloads = _int_or_none(gem.get("downloads"))
    if downloads is None:
        return None

    version = _string_or_none(gem.get("version")) or ""
    version_downloads = _int_or_none(gem.get("version_downloads"))
    published_at = _parse_datetime(gem.get("version_created_at"))
    package_url = _string_or_none(gem.get("project_uri")) or RUBYGEMS_PACKAGE_PAGE.format(
        gem_name=quote(normalized_name, safe="")
    )
    api_url = _api_url(normalized_name)

    version_phrase = f" for version {version}" if version else ""
    content = (
        f"{normalized_name} recorded {downloads:,} total RubyGems downloads"
        f"{version_phrase}."
    )

    return Signal(
        id=_signal_id(normalized_name, version),
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"{normalized_name} RubyGems download trend",
        content=content,
        url=package_url,
        published_at=published_at,
        tags=_build_tags(normalized_name),
        credibility=_credibility(downloads, version_downloads=version_downloads),
        metadata={
            "signal_role": "market",
            "package_ecosystem": "rubygems",
            "gem_name": normalized_name,
            "package_name": normalized_name,
            "version": version,
            "downloads": downloads,
            "download_count": downloads,
            "version_downloads": version_downloads,
            "version_created_at": published_at.isoformat() if published_at else None,
            "source_url": package_url,
            "package_url": package_url,
            "api_url": api_url,
        },
    )


def _api_url(gem_name: str) -> str:
    return RUBYGEMS_DETAILS_API.format(gem_name=quote(gem_name, safe=""))


def _signal_id(gem_name: str, version: str) -> str:
    normalized_version = version.strip().lower() or "unknown"
    return f"rubygems_download_trends:{gem_name}:{normalized_version}"


def _build_tags(gem_name: str) -> list[str]:
    tags = ["ruby", "rubygems", "package", "downloads"]
    tags.extend(part for part in re.split(r"[-_.]+", gem_name.lower()) if part)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(downloads: int, *, version_downloads: int | None) -> float:
    download_score = min(math.log10(downloads + 1) / 8, 0.75)
    version_score = min(math.log10((version_downloads or 0) + 1) / 8, 0.05)
    return min(round(0.2 + download_score + version_score, 3), 1.0)


def _normalize_gem_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


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
