"""Crates.io download trend source adapter — Rust package adoption signals."""

from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

CRATES_DOWNLOADS_API = "https://crates.io/api/v1/crates/{crate_name}/downloads"
CRATES_PACKAGE_URL = "https://crates.io/crates/{crate_name}"


class CratesDownloadTrendsAdapter(SourceAdapter):
    """Fetch recent crates.io download history for configured Rust crates."""

    @property
    def name(self) -> str:
        return "crates_download_trends"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def crates(self) -> list[str]:
        configured = self._configured_terms("crates", [])
        if configured:
            return configured
        return self._configured_terms("packages", [])

    @property
    def window_days(self) -> int:
        return max(int(self._config.get("window_days", 14)), 2)

    @property
    def max_items(self) -> int:
        return max(int(self._config.get("max_items", self._config.get("max_results", 30))), 1)

    @property
    def min_downloads(self) -> int:
        return max(int(self._config.get("min_downloads", 0)), 0)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_crates: set[str] = set()
        item_limit = max(min(limit, self.max_items), 0)
        if item_limit == 0:
            return signals

        async with httpx.AsyncClient(timeout=30) as client:
            for crate_name in self.crates:
                if len(signals) >= item_limit:
                    break

                normalized = _normalize_crate_name(crate_name)
                if not normalized or normalized in seen_crates:
                    continue
                seen_crates.add(normalized)

                payload = await self._fetch_download_history(client, normalized)
                if payload is None:
                    continue

                signal = _download_history_to_signal(
                    payload,
                    fallback_name=normalized,
                    window_days=self.window_days,
                    adapter_name=self.name,
                )
                if signal is None:
                    logger.warning("%s: malformed download history for %s", self.name, normalized)
                    continue
                if signal.metadata["downloads"] < self.min_downloads:
                    continue

                signals.append(signal)

        return signals[:item_limit]

    async def _fetch_download_history(
        self,
        client: httpx.AsyncClient,
        crate_name: str,
    ) -> dict | None:
        url = _api_url(crate_name)
        try:
            response = await fetch_with_retry(
                url,
                client,
                adapter_name=self.name,
                max_retries=2,
                backoff_base=0,
                headers={"User-Agent": "max-crates-download-trends-adapter/0.1"},
            )
            payload = response.json()
        except AdapterFetchError as e:
            logger.warning(
                "%s: failed to fetch download history for %s: %s",
                self.name,
                crate_name,
                e,
            )
            return None
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("%s: request failed for %s: %s", self.name, crate_name, e)
            return None
        except ValueError as e:
            logger.warning(
                "%s: failed to parse download history for %s: %s",
                self.name,
                crate_name,
                e,
            )
            return None

        if not isinstance(payload, dict):
            logger.warning("%s: malformed download history for %s", self.name, crate_name)
            return None
        return payload


def _download_history_to_signal(
    payload: dict,
    *,
    fallback_name: str,
    window_days: int,
    adapter_name: str,
) -> Signal | None:
    crate_name = (
        _normalize_crate_name(payload.get("crate") or payload.get("crate_name"))
        or fallback_name
    )
    if not crate_name:
        return None

    points = _trend_points(payload)
    if not points:
        return None

    window_points = points[-window_days:]
    downloads = sum(point["downloads"] for point in window_points)
    if downloads <= 0:
        return None

    window_start = window_points[0]["date"]
    window_end = window_points[-1]["date"]
    previous_downloads, current_downloads = _split_window_downloads(window_points)
    trend_direction = _trend_direction(previous_downloads, current_downloads)
    package_url = _package_url(crate_name)
    api_url = _api_url(crate_name)

    return Signal(
        id=_signal_id(crate_name, window_start, window_end),
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"{crate_name} crates.io download trend",
        content=(
            f"{crate_name} recorded {downloads:,} crates.io downloads from "
            f"{window_start} to {window_end} ({trend_direction})."
        ),
        url=package_url,
        published_at=_parse_date_as_datetime(window_end),
        tags=_build_tags(crate_name, trend_direction=trend_direction),
        credibility=_credibility(
            downloads,
            previous_downloads=previous_downloads,
            current_downloads=current_downloads,
        ),
        metadata={
            "signal_role": "market",
            "package_ecosystem": "crates.io",
            "crate_name": crate_name,
            "package_name": crate_name,
            "time_window_days": len(window_points),
            "window_days": len(window_points),
            "time_window_start": window_start,
            "time_window_end": window_end,
            "downloads": downloads,
            "download_total": downloads,
            "previous_window_downloads": previous_downloads,
            "current_window_downloads": current_downloads,
            "trend_direction": trend_direction,
            "trend_points": window_points,
            "source_url": package_url,
            "package_url": package_url,
            "api_url": api_url,
        },
    )


def _trend_points(payload: dict) -> list[dict[str, object]]:
    raw_rows = payload.get("version_downloads")
    if raw_rows is None:
        raw_rows = payload.get("downloads") or payload.get("download_history")
    if not isinstance(raw_rows, list):
        return []

    downloads_by_date: dict[str, int] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            continue

        day = _date_string(row.get("date") or row.get("day"))
        downloads = _int_or_none(row.get("downloads") or row.get("num_downloads"))
        if day is None or downloads is None:
            continue
        downloads_by_date[day] = downloads_by_date.get(day, 0) + downloads

    return [
        {"date": day, "downloads": downloads_by_date[day]}
        for day in sorted(downloads_by_date)
    ]


def _split_window_downloads(points: list[dict[str, object]]) -> tuple[int, int]:
    midpoint = max(len(points) // 2, 1)
    previous = sum(int(point["downloads"]) for point in points[:midpoint])
    current = sum(int(point["downloads"]) for point in points[midpoint:])
    return previous, current


def _trend_direction(previous_downloads: int, current_downloads: int) -> str:
    if previous_downloads == current_downloads:
        return "stable"
    if previous_downloads == 0:
        return "improving" if current_downloads > 0 else "stable"

    delta_ratio = (current_downloads - previous_downloads) / previous_downloads
    if delta_ratio >= 0.05:
        return "improving"
    if delta_ratio <= -0.05:
        return "declining"
    return "stable"


def _api_url(crate_name: str) -> str:
    return CRATES_DOWNLOADS_API.format(crate_name=quote(crate_name, safe=""))


def _package_url(crate_name: str) -> str:
    return CRATES_PACKAGE_URL.format(crate_name=quote(crate_name, safe=""))


def _signal_id(crate_name: str, window_start: str, window_end: str) -> str:
    return f"crates_download_trends:{crate_name}:{window_start}:{window_end}"


def _build_tags(crate_name: str, *, trend_direction: str) -> list[str]:
    tags = ["rust", "crates.io", "crate", "package", "downloads", trend_direction]
    tags.extend(part for part in re.split(r"[-_.]+", crate_name.lower()) if part)

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return deduped[:10]


def _credibility(
    downloads: int,
    *,
    previous_downloads: int,
    current_downloads: int,
) -> float:
    download_score = min(math.log10(downloads + 1) / 7, 0.75)
    movement_score = min(abs(current_downloads - previous_downloads) / max(downloads, 1), 0.05)
    return min(round(0.2 + download_score + movement_score, 3), 1.0)


def _normalize_crate_name(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _date_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    raw = value.strip()
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError:
        return None


def _parse_date_as_datetime(value: str) -> datetime | None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def _int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
