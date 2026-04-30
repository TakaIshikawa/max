"""FIRST EPSS source adapter — exploit-likelihood scores for CVEs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

FIRST_EPSS_API_URL = "https://api.first.org/data/v1/epss"
FIRST_EPSS_CVE_URL = "https://www.first.org/epss/data_stats"

_DEFAULT_MIN_EPSS = 0.7
_DEFAULT_MIN_PERCENTILE = 0.95
_MAX_FIRST_LIMIT = 10_000


class EpssScoresAdapter(SourceAdapter):
    """Fetch high-scoring FIRST EPSS CVEs as exploit-likelihood security signals."""

    config_keys = ["base_url", "min_epss", "min_percentile", "date"]
    required_keys: list[str] = []
    description = (
        "Fetches FIRST Exploit Prediction Scoring System CVE scores as "
        "exploit-likelihood security signals."
    )

    def __init__(
        self,
        config: dict | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config=config)
        self._client = client

    @property
    def name(self) -> str:
        return "epss_scores"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    @property
    def base_url(self) -> str:
        return str(self._config.get("base_url", FIRST_EPSS_API_URL))

    @property
    def min_epss(self) -> float:
        return _bounded_probability(self._config.get("min_epss"), _DEFAULT_MIN_EPSS)

    @property
    def min_percentile(self) -> float:
        return _bounded_probability(self._config.get("min_percentile"), _DEFAULT_MIN_PERCENTILE)

    @property
    def date(self) -> str | None:
        value = self._config.get("date")
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        params: dict[str, Any] = {
            "epss-gt": self.min_epss,
            "percentile-gt": self.min_percentile,
            "order": "!epss",
            "limit": min(limit, _MAX_FIRST_LIMIT),
        }
        if self.date:
            params["date"] = self.date

        try:
            if self._client is not None:
                payload = await self._fetch_payload(self._client, params=params)
            else:
                async with httpx.AsyncClient(timeout=30) as client:
                    payload = await self._fetch_payload(client, params=params)
        except AdapterFetchError:
            logger.warning("%s: failed to fetch FIRST EPSS scores", self.name, exc_info=True)
            return []
        except (httpx.RequestError, httpx.TimeoutException):
            logger.warning("%s: failed to fetch FIRST EPSS scores", self.name, exc_info=True)
            return []
        except ValueError:
            logger.warning("%s: failed to parse FIRST EPSS JSON response", self.name, exc_info=True)
            return []

        return parse_epss_scores(payload, adapter_name=self.name, source_url=self.base_url, limit=limit)

    async def _fetch_payload(self, client: httpx.AsyncClient, *, params: dict[str, Any]) -> Any:
        response = await fetch_with_retry(
            self.base_url,
            client,
            adapter_name=self.name,
            headers={"Accept": "application/json"},
            params=params,
            max_retries=0,
        )
        return response.json()


def parse_epss_scores(
    payload: Any,
    *,
    adapter_name: str = "epss_scores",
    source_url: str = FIRST_EPSS_API_URL,
    limit: int = 30,
) -> list[Signal]:
    """Parse a FIRST EPSS API payload into deterministic security signals."""
    if limit <= 0 or not isinstance(payload, dict):
        return []

    rows = payload.get("data")
    if not isinstance(rows, list):
        return []

    signals: list[Signal] = []
    seen_cves: set[str] = set()

    for row in rows:
        if len(signals) >= limit:
            break
        if not isinstance(row, dict):
            continue

        signal = _signal_from_row(row, adapter_name=adapter_name, source_url=source_url)
        if signal is None:
            continue

        cve_id = signal.metadata["cve_id"]
        if cve_id in seen_cves:
            continue
        seen_cves.add(cve_id)
        signals.append(signal)

    return signals


def _signal_from_row(
    row: dict[str, Any],
    *,
    adapter_name: str,
    source_url: str,
) -> Signal | None:
    cve_id = _clean_cve(row.get("cve"))
    epss = _parse_probability(row.get("epss"))
    percentile = _parse_probability(row.get("percentile"))
    observed_at = _parse_observed_at(row.get("date") or row.get("created"))

    if not cve_id or epss is None or percentile is None:
        return None

    observed_date = observed_at.date().isoformat() if observed_at else ""
    content = (
        f"{cve_id} has FIRST EPSS score {epss:.6f} "
        f"and percentile {percentile:.6f}."
    )
    if observed_date:
        content = f"{content} Observed on {observed_date}."

    return Signal(
        id=f"{adapter_name}:{cve_id}:{observed_date or 'latest'}",
        source_type=SignalSourceType.SECURITY,
        source_adapter=adapter_name,
        title=f"FIRST EPSS {cve_id}: {epss:.3f} score ({percentile:.3f} percentile)",
        content=content,
        url=f"{FIRST_EPSS_CVE_URL}?id={cve_id}",
        published_at=observed_at,
        tags=_build_tags(cve_id, epss, percentile),
        credibility=_credibility(epss, percentile),
        metadata={
            "cve_id": cve_id,
            "epss_score": epss,
            "percentile": percentile,
            "observed_date": observed_date,
            "source_url": source_url,
            "signal_role": "problem",
        },
    )


def _clean_cve(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.strip().upper()
    parts = cleaned.split("-")
    if len(parts) != 3 or parts[0] != "CVE":
        return ""
    if not (parts[1].isdigit() and parts[2].isdigit()):
        return ""
    return cleaned


def _parse_probability(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= parsed <= 1.0:
        return parsed
    return None


def _bounded_probability(value: Any, default: float) -> float:
    parsed = _parse_probability(value)
    return default if parsed is None else parsed


def _parse_observed_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _credibility(epss: float, percentile: float) -> float:
    return round(min(1.0, max(0.0, (epss * 0.65) + (percentile * 0.35))), 4)


def _build_tags(cve_id: str, epss: float, percentile: float) -> list[str]:
    tags = [
        "security",
        "epss",
        "first",
        "exploit-likelihood",
        cve_id.lower(),
    ]
    if epss >= 0.9:
        tags.append("critical-epss")
    elif epss >= 0.7:
        tags.append("high-epss")
    if percentile >= 0.95:
        tags.append("top-percentile")
    return tags
