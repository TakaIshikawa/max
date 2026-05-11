"""AngelList source adapter for startup funding and hiring signals."""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

ANGELLIST_API = "https://api.angellist.com/1"
_DEFAULT_MARKETS = ["artificial-intelligence", "developer-tools", "saas"]


def _get_token() -> str | None:
    token = os.environ.get("ANGELLIST_TOKEN") or os.environ.get("ANGELLIST_ACCESS_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["vault", "get", "angellist/token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _name_values(values: Any) -> list[str]:
    names: list[str] = []
    for item in _as_list(values):
        name = item.get("name") if isinstance(item, dict) else item
        if name:
            names.append(str(name))
    return names


def _tags(company: dict[str, Any], market: str) -> list[str]:
    values = {market, "angellist"}
    for key in ("markets", "tags", "technology_tags", "technologies"):
        for name in _name_values(company.get(key)):
            values.add(name.lower())
    return sorted(v for v in values if v)[:10]


def _funding(company: dict[str, Any]) -> dict[str, Any]:
    return company.get("funding") if isinstance(company.get("funding"), dict) else {}


def _funding_rounds(company: dict[str, Any], funding: dict[str, Any]) -> list[Any]:
    return _as_list(company.get("funding_rounds")) or _as_list(funding.get("rounds"))


def _total_raised_usd(company: dict[str, Any], funding: dict[str, Any]) -> float:
    for value in (
        funding.get("total_raised_usd"),
        funding.get("total_raised"),
        company.get("total_raised_usd"),
        company.get("total_raised"),
        company.get("funding_total_usd"),
    ):
        amount = _as_float(value)
        if amount:
            return amount

    total = 0.0
    for round_data in _funding_rounds(company, funding):
        if not isinstance(round_data, dict):
            continue
        total += _as_float(
            round_data.get("amount_usd")
            or round_data.get("raised_amount_usd")
            or round_data.get("amount")
        )
    return total


def _jobs(company: dict[str, Any]) -> list[Any]:
    return _as_list(company.get("jobs")) or _as_list(company.get("job_postings"))


def _team_size(company: dict[str, Any]) -> Any:
    return (
        company.get("team_size")
        or company.get("employee_count")
        or company.get("company_size")
        or company.get("size")
    )


class AngelListAdapter(SourceAdapter):
    """Fetch startup profiles, funding rounds, job postings, and technology tags."""

    @property
    def name(self) -> str:
        return "angellist_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FUNDING.value

    @property
    def markets(self) -> list[str]:
        return self._configured_terms("markets", _DEFAULT_MARKETS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []
        token = _get_token()
        if not token:
            logger.warning("No AngelList API token configured")
            return []

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        signals: list[Signal] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for market in self.markets:
                if len(signals) >= limit:
                    break
                await self._fetch_market(client, market, limit, signals, seen)
        return signals[:limit]

    async def _fetch_market(
        self,
        client: httpx.AsyncClient,
        market: str,
        limit: int,
        signals: list[Signal],
        seen: set[str],
    ) -> None:
        try:
            resp = await fetch_with_retry(
                f"{ANGELLIST_API}/startups",
                client,
                adapter_name=self.name,
                params={"filter": market, "per_page": min(limit, 50)},
            )
            data = resp.json()
        except Exception:
            logger.warning("AngelList fetch failed for %s", market, exc_info=True)
            return
        companies = data.get("startups") or data.get("companies") or []
        for company in companies:
            if len(signals) >= limit or not isinstance(company, dict):
                break
            company_id = str(company.get("id") or company.get("slug") or "")
            if not company_id or company_id in seen:
                continue
            seen.add(company_id)
            signals.append(self._company_to_signal(company, market=market))

    def _company_to_signal(self, company: dict[str, Any], *, market: str) -> Signal:
        funding = _funding(company)
        jobs = _jobs(company)
        amount = _total_raised_usd(company, funding)
        technology_tags = _name_values(company.get("technology_tags")) or _name_values(
            company.get("technologies")
        )
        name = str(company.get("name") or company.get("slug") or "")
        return Signal(
            source_type=SignalSourceType.FUNDING,
            source_adapter=self.name,
            title=name,
            content=str(company.get("product_desc") or company.get("high_concept") or name)[:1000],
            url=str(company.get("angellist_url") or company.get("url") or ""),
            author=None,
            published_at=_parse_dt(funding.get("last_round_at") or company.get("updated_at")),
            tags=_tags(company, market),
            credibility=min((amount / 50_000_000) + len(jobs) * 0.05, 1.0),
            metadata={
                "company_id": str(company.get("id") or company.get("slug") or ""),
                "market": market,
                "team_size": _team_size(company),
                "technology_tags": technology_tags,
                "funding_rounds": _funding_rounds(company, funding),
                "total_raised_usd": amount,
                "job_count": len(jobs),
                "hiring_roles": [
                    str(job.get("title") if isinstance(job, dict) else job) for job in jobs[:10]
                ],
                "trend_signals": {
                    "well_funded": amount >= 10_000_000,
                    "actively_hiring": len(jobs) > 0,
                    "technology_tags": technology_tags[:10],
                },
            },
        )
