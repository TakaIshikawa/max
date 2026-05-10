"""Crunchbase source adapter for company funding data.

Collects company funding, acquisition, and market data via the Crunchbase API.
Fetches organization profiles, funding rounds, and investor activity to
identify well-funded sectors and acquisition trends in the tech industry.
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

CB_API = "https://api.crunchbase.com/api/v4"

_DEFAULT_CATEGORIES = [
    "artificial-intelligence",
    "developer-tools",
    "saas",
    "machine-learning",
]


def _get_api_key() -> str | None:
    """Resolve Crunchbase API key from env or vault."""
    key = os.environ.get("CRUNCHBASE_KEY")
    if key:
        return key
    try:
        result = subprocess.run(
            ["vault", "get", "crunchbase/key"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _parse_dt(s: str | None) -> datetime | None:
    """Parse ISO 8601 or date-only string from Crunchbase API responses."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def _build_tags(categories: list[str], search_category: str) -> list[str]:
    """Build normalized tags from organization categories."""
    tags: set[str] = set()
    cat_map = {
        "artificial-intelligence": "ai",
        "developer-tools": "devtools",
        "saas": "saas",
        "machine-learning": "ml",
        "fintech": "fintech",
        "health-care": "health",
        "enterprise-software": "enterprise",
        "cybersecurity": "security",
        "data-analytics": "analytics",
        "cloud-computing": "cloud",
    }
    for cat in categories:
        mapped = cat_map.get(cat)
        if mapped:
            tags.add(mapped)
        else:
            tags.add(cat)

    search_tag = cat_map.get(search_category, search_category)
    if search_tag:
        tags.add(search_tag)

    tags.add("crunchbase")
    return sorted(tags)[:10]


class CrunchbaseAdapter(SourceAdapter):
    """Fetches organization profiles and funding rounds by category.

    Extracts funding amounts, investors, categories, and employee counts.
    Handles API key authentication and response pagination via ``fetch_with_retry``.
    """

    @property
    def name(self) -> str:
        return "crunchbase_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FUNDING.value

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        api_key = _get_api_key()

        if not api_key:
            logger.warning("No Crunchbase API key configured")
            return signals

        per_category = max(limit // max(len(self.categories), 1), 3)

        async with httpx.AsyncClient(timeout=30) as client:
            for category in self.categories:
                if len(signals) >= limit:
                    break

                params: dict = {
                    "user_key": api_key,
                    "category_groups": category,
                    "sort_order": "desc",
                    "order": "last_funding_at",
                    "limit": min(per_category, 50),
                }

                try:
                    resp = await fetch_with_retry(
                        f"{CB_API}/searches/organizations",
                        client,
                        adapter_name=self.name,
                        params=params,
                    )
                    data = resp.json()
                except Exception:
                    logger.warning(
                        "Crunchbase fetch failed for category: %s",
                        category,
                        exc_info=True,
                    )
                    continue

                for entity in data.get("entities", []):
                    props = entity.get("properties", {})
                    identifier = props.get("identifier", {})
                    permalink = identifier.get("permalink", "")

                    if not permalink or permalink in seen:
                        continue
                    seen.add(permalink)

                    org_name = identifier.get("value", permalink)
                    total_funding = props.get("funding_total", {}).get("value_usd", 0)
                    categories = [
                        c.get("value", "")
                        for c in props.get("categories", [])
                        if c.get("value")
                    ]

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.FUNDING,
                            source_adapter=self.name,
                            title=org_name,
                            content=(props.get("short_description") or org_name)[:500],
                            url=f"https://www.crunchbase.com/organization/{permalink}",
                            author=None,
                            published_at=_parse_dt(props.get("last_funding_at")),
                            tags=_build_tags(categories, category),
                            credibility=min((total_funding or 0) / 100_000_000, 1.0),
                            metadata={
                                "permalink": permalink,
                                "total_funding_usd": total_funding,
                                "num_funding_rounds": props.get("num_funding_rounds", 0),
                                "last_funding_type": props.get("last_funding_type"),
                                "num_employees_enum": props.get("num_employees_enum"),
                                "founded_on": props.get("founded_on"),
                                "categories": categories[:10],
                                "location": props.get("location_identifiers", [{}])[0].get("value")
                                if props.get("location_identifiers")
                                else None,
                                "rank": props.get("rank_org"),
                            },
                        )
                    )

                    if len(signals) >= limit:
                        break

        return signals[:limit]
