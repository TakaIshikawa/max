"""HubSpot quotes import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
HUBSPOT_API = "https://api.hubapi.com"
DEFAULT_QUOTE_PROPERTIES = [
    "hs_title",
    "hs_quote_number",
    "hs_status",
    "hs_quote_amount",
    "hs_currency",
    "hs_expiration_date",
    "hubspot_owner_id",
    "hs_quote_link",
    "hs_pdf_download_link",
    "createdate",
    "hs_lastmodifieddate",
]


class HubSpotQuotesAdapter(SourceAdapter):
    """Fetch HubSpot quotes and convert them to market signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (
                _optional(self._config.get("token"))
                or os.getenv("HUBSPOT_ACCESS_TOKEN")
                or os.getenv("HUBSPOT_TOKEN")
            )
        )
        self.api_url = (
            api_url
            or _optional(self._config.get("api_url"))
            or os.getenv("HUBSPOT_API_URL")
            or HUBSPOT_API
        ).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "hubspot_quotes_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def properties(self) -> list[str]:
        return _strings(self._config.get("properties")) or DEFAULT_QUOTE_PROPERTIES

    @property
    def archived(self) -> bool | None:
        return _bool(self._config.get("archived"))

    @property
    def after(self) -> str | None:
        return _optional(self._config.get("after"))

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("per_page") or self._config.get("limit"),
            default=100,
            maximum=100,
        )

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            quotes = await self._fetch_quotes(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        return [_quote_signal(quote, self.name) for quote in quotes[:limit] if isinstance(quote, dict)]

    async def _fetch_quotes(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        quotes: list[dict[str, Any]] = []
        after = self.after
        while len(quotes) < limit:
            page_limit = min(self.page_size, limit - len(quotes))
            body = await self._get_quotes(client, limit=page_limit, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            quotes.extend(item for item in results if isinstance(item, dict))
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return quotes[:limit]

    async def _get_quotes(
        self,
        client: httpx.AsyncClient,
        *,
        limit: int,
        after: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "properties": self.properties}
        if after:
            params["after"] = after
        if self.archived is not None:
            params["archived"] = str(self.archived).lower()
        try:
            response = await client.get(
                f"{self.api_url}/crm/v3/objects/quotes",
                headers=self._headers,
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot quotes fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "max-hubspot-quotes-import/1",
        }


HubSpotQuoteAdapter = HubSpotQuotesAdapter


def _quote_signal(quote: dict[str, Any], adapter_name: str) -> Signal:
    props = quote.get("properties") if isinstance(quote.get("properties"), dict) else {}
    quote_id = _text(quote.get("id")) or _text(props.get("hs_object_id"))
    title = _text(props.get("hs_title") or props.get("name")) or f"HubSpot quote {quote_id}"
    status = _text(props.get("hs_status") or props.get("quote_status"))
    amount = _number(props.get("hs_quote_amount") or props.get("amount"))
    currency = _text(props.get("hs_currency") or props.get("currency"))
    expiration = _text(props.get("hs_expiration_date") or props.get("expiration_date"))
    owner_id = _text(props.get("hubspot_owner_id") or props.get("hs_owner_id"))
    quote_number = _text(props.get("hs_quote_number") or props.get("quote_number"))
    created_at = props.get("createdate") or quote.get("createdAt")
    updated_at = props.get("hs_lastmodifieddate") or quote.get("updatedAt")
    url = _quote_url(quote, props=props, quote_id=quote_id)
    deal_hints = _deal_association_hints(quote)

    return Signal(
        id=f"hubspot-quote:{quote_id}" if quote_id else "",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=title,
        content=_content(title=title, status=status, amount=amount, currency=currency, expiration=expiration),
        url=url,
        author=owner_id or None,
        published_at=_parse_dt(created_at),
        tags=sorted({"hubspot", "quote", status, currency} - {""})[:10],
        credibility=0.69,
        metadata={
            "signal_role": "market",
            "hubspot_quote_id": quote_id,
            "quote_id": quote_id,
            "title": title,
            "name": title,
            "quote_number": quote_number or None,
            "status": status or None,
            "amount": amount,
            "currency": currency or None,
            "expiration_date": expiration or None,
            "owner_id": owner_id or None,
            "hubspot_owner_id": owner_id or None,
            "created_at": created_at,
            "updated_at": updated_at,
            "url": url,
            "quote_url": url,
            "pdf_url": _optional(props.get("hs_pdf_download_link")),
            "deal_association_hints": deal_hints,
            "associations": quote.get("associations") if isinstance(quote.get("associations"), dict) else {},
            "archived": quote.get("archived"),
            "properties": props,
            "raw": quote,
        },
    )


def _content(
    *,
    title: str,
    status: str,
    amount: float | int | None,
    currency: str,
    expiration: str,
) -> str:
    parts = [f"HubSpot quote {title}"]
    if status:
        parts.append(f"status {status}")
    if amount is not None:
        amount_text = f"{amount:g}" if isinstance(amount, float) else str(amount)
        parts.append(f"amount {amount_text}{f' {currency}' if currency else ''}")
    if expiration:
        parts.append(f"expires {expiration}")
    return "; ".join(parts)


def _quote_url(quote: dict[str, Any], *, props: dict[str, Any], quote_id: str) -> str:
    url = _optional(props.get("hs_quote_link") or quote.get("url") or quote.get("web_url"))
    if url:
        return url
    return f"https://app.hubspot.com/contacts/quote/{quote_id}" if quote_id else ""


def _deal_association_hints(quote: dict[str, Any]) -> list[str]:
    associations = quote.get("associations")
    if not isinstance(associations, dict):
        return []
    deals = associations.get("deals")
    if not isinstance(deals, dict):
        return []
    results = deals.get("results")
    if not isinstance(results, list):
        return []
    hints: list[str] = []
    for item in results:
        if isinstance(item, dict):
            deal_id = _optional(item.get("id") or item.get("toObjectId"))
            if deal_id and deal_id not in hints:
                hints.append(deal_id)
    return hints


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


def _bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _number(value: object) -> float | int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
