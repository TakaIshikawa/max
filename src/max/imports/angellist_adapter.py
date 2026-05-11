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
    except ValueError:
        return None


def _tags(company: dict[str, Any], market: str) -> list[str]:
    values = {market, "angellist"}
    for key in ("markets", "tags", "technology_tags", "technologies"):
        raw = company.get(key)
        if isinstance(raw, list):
            for item in raw:
                values.add(str(item.get("name") if isinstance(item, dict) else item).lower())
    return sorted(v for v in values if v)[:10]


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
        funding = company.get("funding") if isinstance(company.get("funding"), dict) else {}
        jobs = company.get("jobs") if isinstance(company.get("jobs"), list) else []
        amount = funding.get("total_raised_usd") or company.get("total_raised_usd") or 0
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
            credibility=min((float(amount or 0) / 50_000_000) + len(jobs) * 0.05, 1.0),
            metadata={
                "company_id": str(company.get("id") or company.get("slug") or ""),
                "market": market,
                "team_size": company.get("team_size") or company.get("employee_count"),
                "technology_tags": [
                    str(t.get("name") if isinstance(t, dict) else t)
                    for t in company.get("technology_tags", company.get("technologies", []))
                ],
                "funding_rounds": company.get("funding_rounds", funding.get("rounds", [])),
                "total_raised_usd": amount,
                "job_count": len(jobs),
                "hiring_roles": [
                    str(job.get("title") if isinstance(job, dict) else job) for job in jobs[:10]
                ],
            },
        )
