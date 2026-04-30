"""npm download trend source adapter — recent package adoption signals."""

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

NPM_DOWNLOADS_API = "https://api.npmjs.org/downloads/point/{period}/{package}"
NPM_PACKAGE_URL = "https://www.npmjs.com/package/{package}"

_PERIOD_ALIASES = {
    "day": "last-day",
    "week": "last-week",
    "month": "last-month",
    "last_day": "last-day",
    "last_week": "last-week",
    "last_month": "last-month",
    "last-day": "last-day",
    "last-week": "last-week",
    "last-month": "last-month",
}


class NpmDownloadTrendsAdapter(SourceAdapter):
    """Fetch recent npm package download totals from the public npm API."""

    @property
    def name(self) -> str:
        return "npm_download_trends"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def packages(self) -> list[str]:
        return self._configured_terms("packages", [])

    @property
    def period(self) -> str:
        configured = str(self._config.get("period", "last-week")).strip().lower()
        return _PERIOD_ALIASES.get(configured, configured or "last-week")

    @property
    def max_results(self) -> int:
        value = self._config.get("max_results", self._config.get("max_items", 30))
        return max(int(value), 1)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_packages: set[str] = set()
        item_limit = max(min(limit, self.max_results), 0)
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

                row = await self._fetch_downloads(client, normalized)
                if row is None:
                    continue

                downloads = _int_or_none(row.get("downloads"))
                api_package = _normalize_package_name(row.get("package"))
                if downloads is None or not api_package:
                    logger.warning("%s: malformed download row for %s", self.name, normalized)
                    continue

                signals.append(
                    _package_downloads_to_signal(
                        api_package,
                        downloads=downloads,
                        period=self.period,
                        row=row,
                        adapter_name=self.name,
                    )
                )

        return signals[:item_limit]

    async def _fetch_downloads(
        self,
        client: httpx.AsyncClient,
        package: str,
    ) -> dict | None:
        url = _api_url(package, self.period)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-npm-download-trends-adapter/0.1"},
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

        if not isinstance(payload, dict):
            logger.warning("%s: malformed download stats for %s", self.name, package)
            return None
        return payload


def _package_downloads_to_signal(
    package: str,
    *,
    downloads: int,
    period: str,
    row: dict,
    adapter_name: str,
) -> Signal:
    package_url = NPM_PACKAGE_URL.format(package=quote(package, safe="@/"))
    api_url = _api_url(package, period)

    return Signal(
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"{package} npm download trend",
        content=f"{package} recorded {downloads:,} npm downloads in {period}.",
        url=package_url,
        published_at=datetime.now(timezone.utc),
        tags=_build_tags(package, period=period),
        credibility=_credibility(downloads),
        metadata={
            "signal_role": "market",
            "package_name": package,
            "npm_name": package,
            "period": period,
            "downloads": downloads,
            "start": row.get("start"),
            "end": row.get("end"),
            "package_url": package_url,
            "api_url": api_url,
        },
    )


def _api_url(package: str, period: str) -> str:
    return NPM_DOWNLOADS_API.format(
        period=quote(period, safe="-"),
        package=quote(package, safe="@/"),
    )


def _build_tags(package: str, *, period: str) -> list[str]:
    tags = ["javascript", "npm", "package", "downloads", f"downloads-{period}"]
    tags.extend(part for part in re.split(r"[/@._-]+", package.lower()) if part)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(downloads: int) -> float:
    download_score = min(math.log10(downloads + 1) / 8, 0.8)
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
