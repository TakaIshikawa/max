"""GitHub Sponsors import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

GITHUB_GRAPHQL_API = "https://api.github.com/graphql"


class GitHubSponsorsImportAdapter(SourceAdapter):
    """Fetch configured GitHub sponsor accounts as funding/community signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str = GITHUB_GRAPHQL_API,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN")
        self.api_url = api_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "github_sponsors_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FUNDING.value

    @property
    def accounts(self) -> list[str]:
        configured = (
            self._config.get("accounts")
            or self._config.get("sponsor_accounts")
            or self._config.get("users")
            or self._config.get("organizations")
        )
        return _strings(configured)

    @property
    def activity_limit(self) -> int:
        return _positive_int(self._config.get("activity_limit"), default=20, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.accounts:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for account in self.accounts:
                if len(signals) >= limit:
                    break
                payload = await self._fetch_account(client, account)
                if not payload:
                    continue
                signal = _account_signal(payload, adapter_name=self.name)
                if signal:
                    signals.append(signal)
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_account(
        self,
        client: httpx.AsyncClient,
        account: str,
    ) -> dict[str, Any] | None:
        try:
            response = await client.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "Accept": "application/vnd.github+json",
                },
                json={
                    "query": SPONSORS_QUERY,
                    "variables": {
                        "login": account,
                        "first": self.activity_limit,
                    },
                },
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("GitHub Sponsors account fetch failed for %s", account, exc_info=True)
            return None

        if not isinstance(body, dict) or body.get("errors"):
            logger.warning("GitHub Sponsors account fetch returned errors for %s", account)
            return None

        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        account_payload = data.get("user") or data.get("organization")
        return account_payload if isinstance(account_payload, dict) else None


GitHubSponsorsAdapter = GitHubSponsorsImportAdapter


SPONSORS_QUERY = """
query MaxGitHubSponsorsImport($login: String!, $first: Int!) {
  user(login: $login) {
    ...SponsorAccount
  }
  organization(login: $login) {
    ...SponsorAccount
  }
}

fragment SponsorAccount on Sponsorable {
  login
  name
  url
  sponsorsListing {
    name
    shortDescription
    fullDescription
    tiers(first: 20) {
      nodes {
        name
        description
        monthlyPriceInDollars
        isOneTime
        isCustomAmount
      }
    }
  }
  sponsorshipsAsMaintainer(first: $first, activeOnly: false, orderBy: {field: CREATED_AT, direction: DESC}) {
    totalCount
    nodes {
      isActive
      createdAt
      tier {
        name
        monthlyPriceInDollars
        isOneTime
      }
      sponsorEntity {
        ... on User {
          login
          name
          url
        }
        ... on Organization {
          login
          name
          url
        }
      }
    }
  }
}
"""


def _account_signal(account: dict[str, Any], *, adapter_name: str) -> Signal | None:
    login = _text(account.get("login"))
    if not login:
        return None

    listing = account.get("sponsorsListing") if isinstance(account.get("sponsorsListing"), dict) else {}
    sponsorships = (
        account.get("sponsorshipsAsMaintainer")
        if isinstance(account.get("sponsorshipsAsMaintainer"), dict)
        else {}
    )
    nodes = sponsorships.get("nodes") if isinstance(sponsorships.get("nodes"), list) else []
    sponsorship_nodes = [node for node in nodes if isinstance(node, dict)]
    active_nodes = [node for node in sponsorship_nodes if node.get("isActive") is not False]
    tiers = _tiers(listing, sponsorship_nodes)
    sponsor_count = _int_value(sponsorships.get("totalCount"), default=len(sponsorship_nodes))
    active_sponsor_count = len(active_nodes)
    monthly_total = sum(_tier_price(node.get("tier")) for node in active_nodes)
    first_seen = _oldest_created_at(sponsorship_nodes)

    display_name = _text(account.get("name")) or login
    return Signal(
        source_type=SignalSourceType.FUNDING,
        source_adapter=adapter_name,
        title=f"{display_name} has GitHub Sponsors activity",
        content=_content(display_name, sponsor_count, active_sponsor_count, tiers),
        url=_text(account.get("url")) or f"https://github.com/sponsors/{login}",
        author=login,
        published_at=first_seen,
        tags=sorted({"github", "github-sponsors", "funding", "community", "sponsorship"}),
        credibility=_credibility(sponsor_count, active_sponsor_count, monthly_total, tiers),
        metadata={
            "account": login,
            "account_name": _text(account.get("name")) or None,
            "account_url": _text(account.get("url")) or None,
            "sponsor_count": sponsor_count,
            "active_sponsor_count": active_sponsor_count,
            "sampled_sponsor_count": len(sponsorship_nodes),
            "monthly_sponsorship_usd": monthly_total,
            "tiers": tiers,
            "tier_count": len(tiers),
            "recent_sponsors": _recent_sponsors(sponsorship_nodes),
            "listing_name": _text(listing.get("name")) or None,
            "listing_description": _text(listing.get("shortDescription"))
            or _text(listing.get("fullDescription"))
            or None,
            "signal_role": "market",
            "role_hint": "market",
        },
    )


def _content(
    display_name: str,
    sponsor_count: int,
    active_sponsor_count: int,
    tiers: list[dict[str, Any]],
) -> str:
    tier_summary = ", ".join(tier["name"] for tier in tiers[:3] if tier.get("name"))
    parts = [
        f"{display_name} shows GitHub Sponsors funding and community validation.",
        f"Observed {sponsor_count} maintainer sponsorships with {active_sponsor_count} active in the sampled activity.",
    ]
    if tier_summary:
        parts.append(f"Published sponsor tiers include {tier_summary}.")
    return " ".join(parts)


def _tiers(
    listing: dict[str, Any],
    sponsorship_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_tiers = (((listing.get("tiers") or {}).get("nodes")) or [])
    tiers_by_name: dict[str, dict[str, Any]] = {}

    if isinstance(raw_tiers, list):
        for raw in raw_tiers:
            if not isinstance(raw, dict):
                continue
            tier = _normalized_tier(raw)
            if tier["name"]:
                tiers_by_name[tier["name"]] = tier

    for node in sponsorship_nodes:
        raw = node.get("tier")
        if not isinstance(raw, dict):
            continue
        tier = _normalized_tier(raw)
        if tier["name"] and tier["name"] not in tiers_by_name:
            tiers_by_name[tier["name"]] = tier

    return sorted(
        tiers_by_name.values(),
        key=lambda item: (item["monthly_price_usd"] is None, item["monthly_price_usd"] or 0, item["name"]),
    )


def _normalized_tier(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _text(raw.get("name")),
        "description": _text(raw.get("description")) or None,
        "monthly_price_usd": _number(raw.get("monthlyPriceInDollars")),
        "is_one_time": bool(raw.get("isOneTime")),
        "is_custom_amount": bool(raw.get("isCustomAmount")),
    }


def _recent_sponsors(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sponsors: list[dict[str, Any]] = []
    for node in nodes[:10]:
        entity = node.get("sponsorEntity") if isinstance(node.get("sponsorEntity"), dict) else {}
        tier = node.get("tier") if isinstance(node.get("tier"), dict) else {}
        sponsors.append(
            {
                "login": _text(entity.get("login")) or None,
                "name": _text(entity.get("name")) or None,
                "url": _text(entity.get("url")) or None,
                "tier": _text(tier.get("name")) or None,
                "monthly_price_usd": _number(tier.get("monthlyPriceInDollars")),
                "active": node.get("isActive") is not False,
                "created_at": _text(node.get("createdAt")) or None,
            }
        )
    return sponsors


def _credibility(
    sponsor_count: int,
    active_sponsor_count: int,
    monthly_total: float,
    tiers: list[dict[str, Any]],
) -> float:
    score = 0.35
    score += min(sponsor_count, 100) / 250
    score += min(active_sponsor_count, 50) / 125
    score += min(monthly_total, 5000) / 20000
    if tiers:
        score += 0.05
    return round(min(score, 1.0), 3)


def _oldest_created_at(nodes: list[dict[str, Any]]) -> datetime | None:
    parsed = [_parse_dt(node.get("createdAt")) for node in nodes]
    parsed = [item for item in parsed if item is not None]
    return min(parsed) if parsed else None


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    items: list[str] = []
    for item in value:
        text = _text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if result <= 0:
        return default
    return min(result, maximum)


def _tier_price(value: object) -> float:
    if not isinstance(value, dict) or value.get("isOneTime"):
        return 0.0
    return _number(value.get("monthlyPriceInDollars")) or 0.0


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
