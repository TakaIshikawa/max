"""npm downloads time-series adapter for adoption curve analysis.

Collects daily and weekly download counts for JavaScript packages from
the npm registry download counts API. Enables adoption curve analysis
and package growth comparison.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

NPM_API = "https://api.npmjs.org"

_DEFAULT_PACKAGES = ["react", "vue", "angular", "svelte", "next"]


def _format_date(dt: datetime) -> str:
    """Format datetime as YYYY-MM-DD for npm API."""
    return dt.strftime("%Y-%m-%d")


def _calculate_growth_rate(values: list[int]) -> float:
    """Calculate growth rate from a time-series of download counts.

    Returns percentage change from first half to second half average.
    """
    if len(values) < 2:
        return 0.0
    mid = len(values) // 2
    first_half = values[:mid]
    second_half = values[mid:]
    avg_first = sum(first_half) / len(first_half) if first_half else 0
    avg_second = sum(second_half) / len(second_half) if second_half else 0
    if avg_first == 0:
        return 0.0
    return ((avg_second - avg_first) / avg_first) * 100


def _moving_average(values: list[int], window: int = 7) -> list[float]:
    """Calculate simple moving average over download counts."""
    if len(values) < window:
        return [float(sum(values) / len(values))] if values else []
    result: list[float] = []
    for i in range(len(values) - window + 1):
        avg = sum(values[i:i + window]) / window
        result.append(round(avg, 2))
    return result


class NpmDownloadsAdapter(SourceAdapter):
    """Fetches daily/weekly download counts for npm packages.

    Supports date range queries and multi-package comparison.
    Calculates growth rates and moving averages from time-series data.

    Config options:
        packages: list of npm package names to track
        period: time period — 'last-week', 'last-month', or date range
        range_days: number of days to look back (default 30)
    """

    @property
    def name(self) -> str:
        return "npm_downloads_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def packages(self) -> list[str]:
        return self._configured_terms("packages", _DEFAULT_PACKAGES)

    @property
    def range_days(self) -> int:
        val = self._config.get("range_days", 30)
        return int(val) if isinstance(val, (int, float)) else 30

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=self.range_days)
        date_range = f"{_format_date(start_date)}:{_format_date(end_date)}"

        async with httpx.AsyncClient(timeout=30) as client:
            for pkg in self.packages[:limit]:
                sig = await self._fetch_package(client, pkg, date_range)
                if sig:
                    signals.append(sig)

        return signals[:limit]

    async def _fetch_package(
        self, client: httpx.AsyncClient, package: str, date_range: str,
    ) -> Signal | None:
        """Fetch download time-series for a single package."""
        try:
            resp = await fetch_with_retry(
                f"{NPM_API}/downloads/range/{date_range}/{package}",
                client,
                adapter_name=self.name,
            )
            data = resp.json()
        except Exception:
            logger.warning("npm downloads fetch failed: %s", package, exc_info=True)
            return None

        downloads = data.get("downloads", [])
        if not downloads:
            return None

        daily_counts = [d.get("downloads", 0) for d in downloads]
        total = sum(daily_counts)
        growth_rate = _calculate_growth_rate(daily_counts)
        ma = _moving_average(daily_counts)

        return Signal(
            source_type=SignalSourceType.REGISTRY,
            source_adapter=self.name,
            title=data.get("package", package),
            content=f"npm package '{package}' — {total:,} downloads over {len(daily_counts)} days",
            url=f"https://www.npmjs.com/package/{package}",
            published_at=datetime.now(timezone.utc),
            tags=sorted({"npm", "downloads", package}),
            credibility=0.7,
            metadata={
                "package": package,
                "total_downloads": total,
                "daily_average": round(total / len(daily_counts), 2) if daily_counts else 0,
                "growth_rate_pct": round(growth_rate, 2),
                "moving_average_7d": ma,
                "peak_downloads": max(daily_counts) if daily_counts else 0,
                "min_downloads": min(daily_counts) if daily_counts else 0,
                "days_counted": len(daily_counts),
                "start_date": downloads[0].get("day") if downloads else None,
                "end_date": downloads[-1].get("day") if downloads else None,
            },
        )
