"""PyPI download trend source adapter — recent package adoption signals."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

PYPISTATS_RECENT_API = "https://pypistats.org/api/packages/{package}/recent"
PYPI_PROJECT_URL = "https://pypi.org/project/{package}/"

_PERIOD_FIELDS = {
    "day": "last_day",
    "week": "last_week",
    "month": "last_month",
}


class PyPIDownloadTrendsAdapter(SourceAdapter):
    """Fetch recent PyPI package download totals from the pypistats API."""

    @property
    def name(self) -> str:
        return "pypi_download_trends"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def packages(self) -> list[str]:
        return self._configured_terms("packages", [])

    @property
    def period(self) -> str:
        configured = str(self._config.get("period", "week")).strip().lower()
        return configured if configured in _PERIOD_FIELDS else "week"

    @property
    def max_items(self) -> int:
        return max(int(self._config.get("max_items", 30)), 1)

    @property
    def min_downloads(self) -> int:
        return max(int(self._config.get("min_downloads", 0)), 0)

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

                stats = await self._fetch_recent_downloads(client, normalized)
                if stats is None:
                    continue

                downloads = _downloads_for_period(stats, self.period)
                if downloads is None or downloads < self.min_downloads:
                    continue

                signals.append(
                    _package_downloads_to_signal(
                        normalized,
                        downloads=downloads,
                        period=self.period,
                        stats=stats,
                        adapter_name=self.name,
                    )
                )

        return signals[:item_limit]

    async def _fetch_recent_downloads(
        self,
        client: httpx.AsyncClient,
        package: str,
    ) -> dict | None:
        url = PYPISTATS_RECENT_API.format(package=package)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-pypi-download-trends-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch download stats for %s: %s", self.name, package, e)
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, package, e)
            return None
        except ValueError as e:
            logger.warning("%s: failed to parse download stats for %s: %s", self.name, package, e)
            return None

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            logger.warning("%s: malformed download stats for %s", self.name, package)
            return None
        return data


def _package_downloads_to_signal(
    package: str,
    *,
    downloads: int,
    period: str,
    stats: dict,
    adapter_name: str,
) -> Signal:
    package_url = PYPI_PROJECT_URL.format(package=package)
    pypistats_url = PYPISTATS_RECENT_API.format(package=package)
    tags = _build_tags(package, period=period)

    return Signal(
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"{package} PyPI download trend",
        content=f"{package} recorded {downloads:,} PyPI downloads in the last {period}.",
        url=package_url,
        published_at=datetime.now(timezone.utc),
        tags=tags,
        credibility=_credibility(downloads),
        metadata={
            "signal_role": "market",
            "package_name": package,
            "pypi_name": package,
            "period": period,
            "period_field": _PERIOD_FIELDS[period],
            "recent_downloads": downloads,
            "downloads": downloads,
            "last_day": _int_or_none(stats.get("last_day")),
            "last_week": _int_or_none(stats.get("last_week")),
            "last_month": _int_or_none(stats.get("last_month")),
            "package_url": package_url,
            "pypistats_url": pypistats_url,
        },
    )


def _downloads_for_period(stats: dict, period: str) -> int | None:
    return _int_or_none(stats.get(_PERIOD_FIELDS[period]))


def _build_tags(package: str, *, period: str) -> list[str]:
    tags = ["python", "pypi", "package", "downloads", f"downloads-{period}"]
    tags.extend(part for part in re.split(r"[-_.]+", package.lower()) if part)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(downloads: int) -> float:
    download_score = min(math.log10(downloads + 1) / 7, 0.8)
    return min(round(0.2 + download_score, 3), 1.0)


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
