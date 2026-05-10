"""Glassdoor source adapter for employer insights.

Collects employer reviews, salary data, and interview insights via the
Glassdoor API.  Fetches company ratings, CEO approval, and benefit reviews
to identify workplace trends and technology team satisfaction across companies.
"""

from __future__ import annotations

import logging
import os
import subprocess

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GD_API = "https://api.glassdoor.com/api/api.htm"

_DEFAULT_EMPLOYERS = [
    "Google",
    "Microsoft",
    "Amazon",
    "Meta",
    "Apple",
]


def _get_credentials() -> tuple[str | None, str | None]:
    """Resolve Glassdoor partner ID and key from env or vault."""
    partner_id = os.environ.get("GLASSDOOR_PARTNER_ID")
    partner_key = os.environ.get("GLASSDOOR_PARTNER_KEY")
    if partner_id and partner_key:
        return partner_id, partner_key
    try:
        id_result = subprocess.run(
            ["vault", "get", "glassdoor/partner_id"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        key_result = subprocess.run(
            ["vault", "get", "glassdoor/partner_key"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pid = id_result.stdout.strip() if id_result.returncode == 0 else None
        pkey = key_result.stdout.strip() if key_result.returncode == 0 else None
        if pid and pkey:
            return pid, pkey
    except Exception:
        pass
    return None, None


def _build_tags(industry: str | None, sector: str | None) -> list[str]:
    """Build normalized tags from employer industry and sector."""
    tags: set[str] = set()
    industry_map = {
        "Internet": "internet",
        "Computer Hardware & Software": "software",
        "Information Technology": "it",
        "Enterprise Software & Network Solutions": "enterprise",
        "Financial Services": "fintech",
        "Biotech & Pharmaceuticals": "biotech",
        "Telecommunications": "telecom",
    }
    if industry:
        mapped = industry_map.get(industry, industry.lower().replace(" ", "-"))
        tags.add(mapped)
    if sector:
        tags.add(sector.lower().replace(" ", "-"))

    tags.add("glassdoor")
    return sorted(tags)[:10]


class GlassdoorAdapter(SourceAdapter):
    """Fetches company reviews, ratings, and salary data.

    Extracts overall rating, CEO approval, and recommend-to-friend scores.
    Handles API partner authentication and pagination via ``fetch_with_retry``.
    """

    @property
    def name(self) -> str:
        return "glassdoor_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SURVEY.value

    @property
    def employers(self) -> list[str]:
        return self._configured_terms("employers", _DEFAULT_EMPLOYERS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[int] = set()
        partner_id, partner_key = _get_credentials()

        if not partner_id or not partner_key:
            logger.warning("No Glassdoor partner credentials configured")
            return signals

        async with httpx.AsyncClient(timeout=30) as client:
            for employer_name in self.employers:
                if len(signals) >= limit:
                    break

                params: dict = {
                    "t.p": partner_id,
                    "t.k": partner_key,
                    "format": "json",
                    "v": "1",
                    "action": "employers",
                    "q": employer_name,
                    "ps": min(limit, 20),
                }

                try:
                    resp = await fetch_with_retry(
                        GD_API,
                        client,
                        adapter_name=self.name,
                        params=params,
                    )
                    data = resp.json()
                except Exception:
                    logger.warning(
                        "Glassdoor fetch failed for employer: %s",
                        employer_name,
                        exc_info=True,
                    )
                    continue

                response = data.get("response", {})
                for employer in response.get("employers", []):
                    emp_id = employer.get("id")
                    if not emp_id or emp_id in seen:
                        continue
                    seen.add(emp_id)

                    overall_rating = employer.get("overallRating", 0)
                    industry = employer.get("industry")
                    sector = employer.get("sectorName")

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.SURVEY,
                            source_adapter=self.name,
                            title=employer.get("name", ""),
                            content=f"Overall rating: {overall_rating}/5"[:500],
                            url=employer.get("featuredReview", {}).get("attributionURL", ""),
                            author=None,
                            published_at=None,
                            tags=_build_tags(industry, sector),
                            credibility=min(overall_rating / 5.0, 1.0) if overall_rating else 0.5,
                            metadata={
                                "employer_id": emp_id,
                                "overall_rating": overall_rating,
                                "ceo_approval": employer.get("ceo", {}).get("pctApprove"),
                                "recommend_to_friend": employer.get("recommendToFriendRating"),
                                "number_of_ratings": employer.get("numberOfRatings", 0),
                                "industry": industry,
                                "sector": sector,
                                "revenue": employer.get("revenue"),
                                "size": employer.get("size"),
                                "compensation_rating": employer.get("compensationAndBenefitsRating"),
                                "culture_rating": employer.get("cultureAndValuesRating"),
                                "work_life_rating": employer.get("workLifeBalanceRating"),
                            },
                        )
                    )

                    if len(signals) >= limit:
                        break

        return signals[:limit]
