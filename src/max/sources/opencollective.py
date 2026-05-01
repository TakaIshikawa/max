"""OpenCollective source adapter -- open-source project funding signals."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

OPENCOLLECTIVE_GRAPHQL = "https://api.opencollective.com/graphql/v2"

_DEFAULT_SEARCH_TERMS = ["open source", "developer tools", "python", "javascript"]

_ACCOUNT_FIELDS = """
fragment CollectiveFields on Account {
  id
  slug
  name
  description
  longDescription
  website
  type
  tags
  imageUrl
  currency
  createdAt
  updatedAt
  balance {
    value
    currency
  }
  totalAmountReceived {
    value
    currency
  }
  yearlyBudget {
    value
    currency
  }
  members(role: BACKER, limit: 0) {
    totalCount
  }
  transactions(type: CREDIT, limit: 1) {
    totalCount
    nodes {
      createdAt
      amount {
        value
        currency
      }
    }
  }
}
"""

ACCOUNT_BY_SLUG_QUERY = (
    _ACCOUNT_FIELDS
    + """
query OpenCollectiveAccountBySlug($slug: String!) {
  account(slug: $slug) {
    ...CollectiveFields
  }
}
"""
)

SEARCH_ACCOUNTS_QUERY = (
    _ACCOUNT_FIELDS
    + """
query OpenCollectiveSearchAccounts($query: String!, $limit: Int!) {
  accounts(searchTerm: $query, type: COLLECTIVE, limit: $limit) {
    nodes {
      ...CollectiveFields
    }
  }
}
"""
)


class OpenCollectiveAdapter(SourceAdapter):
    """Fetch OpenCollective project funding and backer momentum signals."""

    @property
    def name(self) -> str:
        return "opencollective"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FUNDING.value

    @property
    def slugs(self) -> list[str]:
        return _string_list(self._config.get("slugs") or self._config.get("collectives"))

    @property
    def search_terms(self) -> list[str]:
        return self._configured_terms(
            "search_terms",
            self._config.get("queries", _DEFAULT_SEARCH_TERMS),
        )

    @property
    def graphql_url(self) -> str:
        value = self._config.get("graphql_url") or self._config.get("api_url")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return OPENCOLLECTIVE_GRAPHQL

    @property
    def timeout(self) -> float:
        value = self._config.get("timeout", 30)
        if isinstance(value, bool):
            return 30.0
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 30.0
        return parsed if parsed > 0 else 30.0

    @property
    def max_results_per_query(self) -> int:
        return _positive_int(self._config.get("max_results_per_query"), default=20)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        signals: list[Signal] = []
        seen_urls: set[str] = set()

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "max-opencollective-adapter",
        }

        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            for slug in self.slugs:
                if len(signals) >= limit:
                    break
                collective = await self._fetch_collective_by_slug(client, slug)
                _append_signal(
                    signals,
                    seen_urls,
                    collective,
                    adapter_name=self.name,
                    query=None,
                    graphql_url=self.graphql_url,
                    limit=limit,
                )

            remaining = limit - len(signals)
            if remaining <= 0:
                return signals[:limit]

            per_query = min(self.max_results_per_query, max(remaining, 1))
            for term in self.search_terms:
                if len(signals) >= limit:
                    break
                collectives = await self._search_collectives(client, term, per_query)
                for collective in collectives:
                    if len(signals) >= limit:
                        break
                    _append_signal(
                        signals,
                        seen_urls,
                        collective,
                        adapter_name=self.name,
                        query=term,
                        graphql_url=self.graphql_url,
                        limit=limit,
                    )

        return signals[:limit]

    async def _fetch_collective_by_slug(
        self,
        client: httpx.AsyncClient,
        slug: str,
    ) -> dict[str, Any] | None:
        slug = slug.strip()
        if not slug:
            return None

        data = await self._post_graphql(
            client,
            ACCOUNT_BY_SLUG_QUERY,
            {"slug": slug},
            context=f"slug {slug}",
        )
        account = data.get("account") if isinstance(data, dict) else None
        return account if isinstance(account, dict) else None

    async def _search_collectives(
        self,
        client: httpx.AsyncClient,
        term: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        term = term.strip()
        if not term:
            return []

        data = await self._post_graphql(
            client,
            SEARCH_ACCOUNTS_QUERY,
            {"query": term, "limit": limit},
            context=f"search term {term}",
        )
        accounts = data.get("accounts") if isinstance(data, dict) else None
        nodes = _nodes(accounts)
        return [node for node in nodes if isinstance(node, dict)]

    async def _post_graphql(
        self,
        client: httpx.AsyncClient,
        query: str,
        variables: dict[str, Any],
        *,
        context: str,
    ) -> dict[str, Any]:
        try:
            response = await client.post(
                self.graphql_url,
                json={"query": query, "variables": variables},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            logger.warning(
                "OpenCollective fetch failed for %s",
                context,
                exc_info=True,
            )
            return {}

        if not isinstance(payload, dict):
            logger.warning("OpenCollective returned non-object payload for %s", context)
            return {}

        errors = payload.get("errors")
        if errors:
            logger.warning("OpenCollective GraphQL errors for %s: %s", context, errors)
            return {}

        data = payload.get("data")
        return data if isinstance(data, dict) else {}


def _append_signal(
    signals: list[Signal],
    seen_urls: set[str],
    collective: dict[str, Any] | None,
    *,
    adapter_name: str,
    query: str | None,
    graphql_url: str,
    limit: int,
) -> None:
    if len(signals) >= limit or not collective:
        return

    signal = _to_signal(
        collective,
        adapter_name=adapter_name,
        query=query,
        graphql_url=graphql_url,
    )
    if signal is None:
        return

    dedupe_url = _normalize_url(signal.url)
    if dedupe_url in seen_urls:
        return
    seen_urls.add(dedupe_url)
    signals.append(signal)


def _to_signal(
    collective: dict[str, Any],
    *,
    adapter_name: str,
    query: str | None,
    graphql_url: str,
) -> Signal | None:
    slug = _string_value(collective.get("slug"))
    name = _string_value(collective.get("name")) or slug
    if not slug and not name:
        return None

    url = _collective_url(collective, slug)
    if not url:
        return None

    total_received = _money_value(
        collective.get("totalAmountReceived"),
        fallback=collective.get("totalAmountReceivedInCents"),
    )
    balance = _money_value(collective.get("balance"), fallback=collective.get("balance"))
    yearly_budget = _money_value(
        collective.get("yearlyBudget"),
        fallback=collective.get("yearlyIncome"),
    )
    currency = (
        _money_currency(collective.get("totalAmountReceived"))
        or _money_currency(collective.get("balance"))
        or _string_value(collective.get("currency"))
    )
    backers_count = _count_from_connection(collective.get("members"))
    if backers_count is None:
        backers_count = _int_value(collective.get("backersCount"))
    transactions_count = _count_from_connection(collective.get("transactions"))
    latest_contribution_at = _latest_transaction_at(collective.get("transactions"))

    description = (
        _string_value(collective.get("description"))
        or _string_value(collective.get("longDescription"))
        or ""
    )
    content = _content(
        name=name,
        description=description,
        total_received=total_received,
        yearly_budget=yearly_budget,
        backers_count=backers_count,
        currency=currency,
    )

    metadata = {
        "opencollective_id": _string_value(collective.get("id")),
        "slug": slug,
        "collective_url": url,
        "graphql_url": graphql_url,
        "source_query": query,
        "account_type": _string_value(collective.get("type")),
        "currency": currency,
        "balance": balance,
        "total_amount_received": total_received,
        "yearly_budget": yearly_budget,
        "backers_count": backers_count,
        "transactions_count": transactions_count,
        "latest_contribution_at": latest_contribution_at.isoformat()
        if latest_contribution_at
        else None,
        "website": _string_value(collective.get("website")),
        "signal_role": "market",
        "role_hint": "market",
    }

    return Signal(
        source_type=SignalSourceType.FUNDING,
        source_adapter=adapter_name,
        title=f"{name} has OpenCollective funding momentum",
        content=content,
        url=url,
        author=name,
        published_at=latest_contribution_at or _parse_dt(collective.get("updatedAt")),
        tags=_build_tags(collective),
        credibility=_credibility(total_received, backers_count),
        metadata={key: value for key, value in metadata.items() if value not in (None, "")},
    )


def _content(
    *,
    name: str,
    description: str,
    total_received: float | None,
    yearly_budget: float | None,
    backers_count: int | None,
    currency: str | None,
) -> str:
    parts = [description.strip()] if description.strip() else []
    metrics: list[str] = []
    if total_received is not None:
        metrics.append(f"{_format_money(total_received, currency)} total received")
    if yearly_budget is not None:
        metrics.append(f"{_format_money(yearly_budget, currency)} yearly budget")
    if backers_count is not None:
        metrics.append(f"{backers_count} backers")

    if metrics:
        parts.append(f"{name} reports {', '.join(metrics)} on OpenCollective.")
    else:
        parts.append(f"{name} maintains an OpenCollective funding profile.")
    parts.append("Funding and backer activity can indicate active community budget and demand.")
    return " ".join(parts)[:1000]


def _collective_url(collective: dict[str, Any], slug: str) -> str:
    url = _string_value(collective.get("url") or collective.get("profile"))
    if url:
        return url
    return f"https://opencollective.com/{slug}" if slug else ""


def _nodes(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        nodes = value.get("nodes")
        if isinstance(nodes, list):
            return nodes
        edges = value.get("edges")
        if isinstance(edges, list):
            return [
                edge.get("node")
                for edge in edges
                if isinstance(edge, dict) and isinstance(edge.get("node"), dict)
            ]
    return []


def _count_from_connection(value: Any) -> int | None:
    if isinstance(value, dict):
        count = _int_value(value.get("totalCount"))
        if count is not None:
            return count
        count = _int_value(value.get("count"))
        if count is not None:
            return count
        nodes = _nodes(value)
        return len(nodes) if nodes else None
    if isinstance(value, list):
        return len(value)
    return None


def _latest_transaction_at(value: Any) -> datetime | None:
    dates = [
        parsed
        for node in _nodes(value)
        if isinstance(node, dict)
        for parsed in [_parse_dt(node.get("createdAt"))]
        if parsed is not None
    ]
    return max(dates) if dates else None


def _money_value(value: Any, *, fallback: Any = None) -> float | None:
    if isinstance(value, dict):
        parsed = _float_value(value.get("value"))
        if parsed is not None:
            return parsed
        parsed = _float_value(value.get("amount"))
        if parsed is not None:
            return parsed / 100 if abs(parsed) >= 100 else parsed
    parsed = _float_value(fallback if fallback is not None else value)
    if parsed is None:
        return None
    return parsed / 100 if abs(parsed) >= 100 else parsed


def _money_currency(value: Any) -> str | None:
    if isinstance(value, dict):
        return _string_value(value.get("currency")) or None
    return None


def _build_tags(collective: dict[str, Any]) -> list[str]:
    tags = {"funding", "opencollective", "sponsorship"}
    raw_tags = collective.get("tags")
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            value = _string_value(tag).lower().replace(" ", "-")
            if value:
                tags.add(value)

    text = " ".join(
        [
            _string_value(collective.get("name")),
            _string_value(collective.get("description")),
            _string_value(collective.get("longDescription")),
        ]
    ).lower()
    keyword_map = {
        "open source": "open-source",
        "developer": "devtools",
        "javascript": "javascript",
        "typescript": "typescript",
        "python": "python",
        "ai": "ai",
        "security": "security",
        "data": "data",
    }
    for needle, tag in keyword_map.items():
        if needle in text:
            tags.add(tag)
    return sorted(tags)[:10]


def _credibility(total_received: float | None, backers_count: int | None) -> float:
    received_score = min((total_received or 0.0) / 100_000, 1.0) * 0.55
    backer_score = min((backers_count or 0) / 500, 1.0) * 0.35
    return round(max(0.35, min(received_score + backer_score + 0.1, 1.0)), 3)


def _normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _format_money(value: float, currency: str | None) -> str:
    prefix = "$" if not currency or currency.upper() == "USD" else f"{currency.upper()} "
    return f"{prefix}{value:,.0f}"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        return []

    seen: set[str] = set()
    values: list[str] = []
    for item in raw_values:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return values


def _positive_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _int_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
