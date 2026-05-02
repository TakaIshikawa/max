"""Hex.pm download trend source adapter - BEAM package adoption signals."""

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

DEFAULT_PACKAGES = [
    "phoenix",
    "ecto",
    "plug",
    "jason",
    "oban",
    "telemetry",
    "cowboy",
    "tesla",
]

_PERIOD_FIELDS = {
    "day": "day",
    "daily": "day",
    "last-day": "day",
    "last_day": "day",
    "week": "week",
    "weekly": "week",
    "last-week": "week",
    "last_week": "week",
    "recent": "recent",
    "all": "all",
    "total": "all",
}


class HexPmDownloadTrendsAdapter(SourceAdapter):
    """Fetch Hex.pm download totals for configured BEAM packages."""

    @property
    def name(self) -> str:
        return "hexpm_download_trends"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def packages(self) -> list[str]:
        return self._configured_terms("packages", DEFAULT_PACKAGES)

    @property
    def period(self) -> str:
        configured = str(self._config.get("period", "recent")).strip().lower()
        return _PERIOD_FIELDS.get(configured, configured or "recent")

    @property
    def max_items(self) -> int:
        return max(int(self._config.get("max_items", self._config.get("max_results", 30))), 1)

    @property
    def min_downloads(self) -> int:
        return max(int(self._config.get("min_downloads", 0)), 0)

    @property
    def api_base_url(self) -> str:
        return str(self._config.get("api_base_url", HEXPM_API_BASE_URL)).rstrip("/")

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

                payload = await self._fetch_package_downloads(client, normalized)
                if payload is None:
                    continue

                signal = _package_downloads_to_signal(
                    payload,
                    fallback_name=normalized,
                    period=self.period,
                    adapter_name=self.name,
                    api_base_url=self.api_base_url,
                )
                if signal is None:
                    logger.warning("%s: malformed download stats for %s", self.name, normalized)
                    continue
                if signal.metadata["downloads"] < self.min_downloads:
                    continue

                signals.append(signal)

        return signals[:item_limit]

    async def _fetch_package_downloads(
        self,
        client: httpx.AsyncClient,
        package: str,
    ) -> dict | None:
        url = _api_url(self.api_base_url, package)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-hexpm-download-trends-adapter/0.1"},
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
    package: dict,
    *,
    fallback_name: str,
    period: str,
    adapter_name: str,
    api_base_url: str,
) -> Signal | None:
    package_name = _normalize_package_name(package.get("name")) or fallback_name
    if not package_name:
        return None

    downloads = _downloads(package.get("downloads"))
    selected_downloads = downloads.get(period)
    if selected_downloads is None:
        return None

    updated_at = _parse_datetime(package.get("updated_at"))
    package_url = _package_url(package_name)
    api_url = _api_url(api_base_url, package_name)
    time_window = _time_window_label(period)

    return Signal(
        id=_signal_id(package_name, period),
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"{package_name} Hex.pm download trend",
        content=(
            f"{package_name} recorded {selected_downloads:,} Hex.pm downloads "
            f"for {time_window}."
        ),
        url=package_url,
        published_at=updated_at,
        tags=_build_tags(package_name, period=period),
        credibility=_credibility(selected_downloads, total_downloads=downloads.get("all", 0)),
        metadata={
            "signal_role": "market",
            "package_ecosystem": "hexpm",
            "package_name": package_name,
            "hexpm_name": package_name,
            "period": period,
            "time_window": time_window,
            "downloads": selected_downloads,
            "download_count": selected_downloads,
            "total_downloads": downloads.get("all", 0),
            "recent_downloads": downloads.get("recent", 0),
            "daily_downloads": downloads.get("day", 0),
            "weekly_downloads": downloads.get("week", 0),
            "updated_at": updated_at.isoformat() if updated_at else None,
            "source_url": package_url,
            "package_url": package_url,
            "api_url": api_url,
        },
    )


def _downloads(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        parsed = _int_or_none(value)
        return {} if parsed is None else {"all": parsed}

    downloads: dict[str, int] = {}
    for key in ("all", "recent", "day", "week"):
        parsed = _int_or_none(value.get(key))
        if parsed is not None:
            downloads[key] = parsed
    return downloads


def _api_url(api_base_url: str, package: str) -> str:
    return f"{api_base_url}/packages/{quote(package, safe='')}"


def _package_url(package: str) -> str:
    return HEXPM_PACKAGE_URL.format(package=quote(package, safe=""))


def _signal_id(package_name: str, period: str) -> str:
    return f"hexpm_download_trends:{package_name}:{period}"


def _time_window_label(period: str) -> str:
    if period == "all":
        return "all time"
    if period == "day":
        return "the last day"
    if period == "week":
        return "the last week"
    return "the recent window"


def _build_tags(package_name: str, *, period: str) -> list[str]:
    tags = ["elixir", "erlang", "beam", "hexpm", "package", "downloads", f"downloads-{period}"]
    tags.extend(part for part in re.split(r"[-_.]+", package_name.lower()) if part)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(downloads: int, *, total_downloads: int) -> float:
    download_score = min(math.log10(downloads + 1) / 7, 0.65)
    total_score = min(math.log10(total_downloads + 1) / 8, 0.1)
    return min(round(0.2 + download_score + total_score, 3), 1.0)


def _normalize_package_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


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
