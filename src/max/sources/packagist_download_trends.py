"""Packagist download trend source adapter - PHP package adoption signals."""

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


class PackagistDownloadTrendsAdapter(SourceAdapter):
    """Fetch Packagist package download totals for configured PHP packages."""

    @property
    def name(self) -> str:
        return "packagist_download_trends"

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
    def base_url(self) -> str:
        configured = str(self._config.get("base_url", PACKAGIST_BASE_URL)).strip()
        return (configured or PACKAGIST_BASE_URL).rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_packages: set[str] = set()
        item_limit = max(min(limit, self.max_items), 0)
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

                payload = await self._fetch_package_metadata(client, normalized)
                if payload is None:
                    continue

                signal = _package_metadata_to_signal(
                    payload,
                    fallback_name=normalized,
                    base_url=self.base_url,
                    adapter_name=self.name,
                )
                if signal is None:
                    logger.warning("%s: malformed package download stats for %s", self.name, normalized)
                    continue

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
                headers={"User-Agent": "max-packagist-download-trends-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning(
                "%s: failed to fetch download stats for %s: %s",
                self.name,
                package_name,
                e,
            )
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, package_name, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse download stats for %s: %s", self.name, package_name, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed package metadata for %s", self.name, package_name)
            return None
        return payload


def _package_metadata_to_signal(
    payload: dict,
    *,
    fallback_name: str,
    base_url: str,
    adapter_name: str,
) -> Signal | None:
    package = payload.get("package")
    if not isinstance(package, dict):
        return None

    package_name = _normalize_package_name(package.get("name")) or fallback_name
    if not package_name:
        return None

    downloads_total = _download_count(package.get("downloads"), "total")
    if downloads_total is None:
        return None

    downloads_monthly = _download_count(package.get("downloads"), "monthly")
    downloads_daily = _download_count(package.get("downloads"), "daily")
    repository = _string_or_none(package.get("repository")) or _latest_repository(package)
    package_url = _string_or_none(package.get("url")) or _package_url(package_name, base_url=base_url)
    api_url = _api_url(package_name, base_url=base_url)
    published_at = _parse_datetime(package.get("time")) or _latest_release_time(package)
    trend_points = _trend_points(
        downloads_total=downloads_total,
        downloads_monthly=downloads_monthly,
        downloads_daily=downloads_daily,
    )

    return Signal(
        id=_signal_id(package_name),
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"{package_name} Packagist download trend",
        content=_content(
            package_name,
            downloads_total=downloads_total,
            downloads_monthly=downloads_monthly,
            downloads_daily=downloads_daily,
        ),
        url=package_url,
        published_at=published_at,
        tags=_build_tags(package_name),
        credibility=_credibility(
            downloads_total,
            downloads_monthly=downloads_monthly,
            downloads_daily=downloads_daily,
        ),
        metadata={
            "signal_role": "market",
            "package_ecosystem": "packagist",
            "package_name": package_name,
            "packagist_name": package_name,
            "downloads": downloads_total,
            "download_count": downloads_total,
            "downloads_total": downloads_total,
            "downloads_monthly": downloads_monthly,
            "downloads_daily": downloads_daily,
            "repository": repository,
            "repository_url": repository,
            "source_url": package_url,
            "package_url": package_url,
            "api_url": api_url,
            "trend_points": trend_points,
        },
    )


def _api_url(package_name: str, *, base_url: str) -> str:
    return f"{base_url}/packages/{quote(package_name, safe='/')}.json"


def _package_url(package_name: str, *, base_url: str) -> str:
    return f"{base_url}/packages/{quote(package_name, safe='/')}"


def _signal_id(package_name: str) -> str:
    return f"packagist_download_trends:{package_name}"


def _content(
    package_name: str,
    *,
    downloads_total: int,
    downloads_monthly: int | None,
    downloads_daily: int | None,
) -> str:
    parts = [f"{package_name} recorded {downloads_total:,} total Packagist downloads"]
    if downloads_monthly is not None:
        parts.append(f"{downloads_monthly:,} monthly")
    if downloads_daily is not None:
        parts.append(f"{downloads_daily:,} daily")
    return ", ".join(parts) + "."


def _trend_points(
    *,
    downloads_total: int,
    downloads_monthly: int | None,
    downloads_daily: int | None,
) -> list[dict[str, object]]:
    points: list[dict[str, object]] = [{"window": "total", "downloads": downloads_total}]
    if downloads_monthly is not None:
        points.append({"window": "monthly", "downloads": downloads_monthly})
    if downloads_daily is not None:
        points.append({"window": "daily", "downloads": downloads_daily})
    return points


def _build_tags(package_name: str) -> list[str]:
    tags = ["php", "packagist", "package", "downloads"]
    tags.extend(part for part in re.split(r"[/._-]+", package_name.lower()) if part)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(
    downloads_total: int,
    *,
    downloads_monthly: int | None,
    downloads_daily: int | None,
) -> float:
    total_score = min(math.log10(downloads_total + 1) / 8, 0.7)
    monthly_score = min(math.log10((downloads_monthly or 0) + 1) / 8, 0.08)
    daily_score = min(math.log10((downloads_daily or 0) + 1) / 8, 0.02)
    return min(round(0.2 + total_score + monthly_score + daily_score, 3), 1.0)


def _latest_repository(package: dict) -> str | None:
    latest = _latest_version(package)
    source = latest.get("source") if isinstance(latest.get("source"), dict) else {}
    support = latest.get("support") if isinstance(latest.get("support"), dict) else {}
    return _string_or_none(source.get("url")) or _string_or_none(support.get("source"))


def _latest_release_time(package: dict) -> datetime | None:
    latest = _latest_version(package)
    return _parse_datetime(latest.get("time"))


def _latest_version(package: dict) -> dict:
    versions = package.get("versions")
    if isinstance(versions, dict):
        candidates = [value for value in versions.values() if isinstance(value, dict)]
    elif isinstance(versions, list):
        candidates = [value for value in versions if isinstance(value, dict)]
    else:
        candidates = []

    if not candidates:
        return {}

    return max(
        candidates,
        key=lambda version: (
            _parse_datetime(version.get("time")) or datetime.min.replace(tzinfo=timezone.utc),
            str(version.get("version_normalized") or version.get("version") or ""),
        ),
    )


def _download_count(value: object, key: str) -> int | None:
    if not isinstance(value, dict):
        return None
    return _int_or_none(value.get(key))


def _normalize_package_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().strip("/")


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
