"""Zendesk ticket satisfaction ratings import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskTicketSatisfactionRatingsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        oauth_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        configured_base = base_url or _optional(self._config.get("base_url")) or os.getenv("ZENDESK_BASE_URL")
        subdomain = _optional(self._config.get("subdomain")) or os.getenv("ZENDESK_SUBDOMAIN")
        self.base_url = (configured_base or (f"https://{subdomain}.zendesk.com" if subdomain else "")).rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("ZENDESK_EMAIL"))
        self.api_token = api_token if api_token is not None else (
            _optional(self._config.get("api_token"))
            or _optional(self._config.get("token"))
            or os.getenv("ZENDESK_API_TOKEN")
        )
        self.oauth_token = oauth_token if oauth_token is not None else (
            _optional(self._config.get("oauth_token")) or os.getenv("ZENDESK_OAUTH_TOKEN")
        )
        self._client = client

    @property
    def name(self) -> str:
        return "zendesk_ticket_satisfaction_ratings_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def ticket_ids(self) -> list[str]:
        return _strings(self._config.get("ticket_ids") or self._config.get("ticket_id"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=100, maximum=100)

    @property
    def _has_auth(self) -> bool:
        return bool(self.oauth_token or (self.email and self.api_token))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.ticket_ids and self._has_auth):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            ratings: list[tuple[str, dict[str, Any]]] = []
            for ticket_id in self.ticket_ids:
                if len(ratings) >= limit:
                    break
                rating = await self._fetch_ticket_rating(client, ticket_id=ticket_id)
                if rating:
                    ratings.append((ticket_id, rating))
            return [
                _rating_signal(ticket_id, rating, self.name, self.base_url)
                for ticket_id, rating in ratings[:limit]
            ]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_ticket_rating(
        self,
        client: httpx.AsyncClient,
        *,
        ticket_id: str,
    ) -> dict[str, Any]:
        body = await self._get(
            client,
            url=f"{self.base_url}/api/v2/tickets/{ticket_id}/satisfaction_rating.json",
            params={"page[size]": self.page_size},
        )
        rating = body.get("satisfaction_rating")
        return rating if isinstance(rating, dict) else {}

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": "max-zendesk-ticket-satisfaction-ratings-import/1"}
        auth = None
        if self.oauth_token:
            headers["Authorization"] = f"Bearer {self.oauth_token}"
        else:
            auth = (f"{self.email}/token", self.api_token or "")
        try:
            response = await client.get(url, headers=headers, auth=auth, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Zendesk ticket satisfaction rating fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


ZendeskTicketSatisfactionRatingsAdapter = ZendeskTicketSatisfactionRatingsImportAdapter


def _rating_signal(
    ticket_id: str,
    rating: dict[str, Any],
    adapter_name: str,
    base_url: str,
) -> Signal:
    rating_id = _text(rating.get("id")) or _text(rating.get("created_at")) or "latest"
    score = _optional(rating.get("score"))
    reason = _optional(rating.get("reason") or rating.get("reason_code"))
    comment = _optional(rating.get("comment"))
    requester_id = _optional(rating.get("requester_id"))
    title_score = score or "unknown"
    return Signal(
        id=f"zendesk-ticket-satisfaction-rating:{ticket_id}:{rating_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"Zendesk ticket {ticket_id} satisfaction rating {title_score}",
        content=_rating_content(score=score, reason=reason, comment=comment)[:1000],
        url=f"{base_url}/agent/tickets/{ticket_id}",
        author=requester_id,
        published_at=_parse_dt(rating.get("created_at")),
        tags=sorted({"zendesk", "ticket-satisfaction-rating", f"rating-{score.lower()}" if score else ""} - {""})[:10],
        credibility=0.7,
        metadata={
            "rating_id": rating.get("id"),
            "score": rating.get("score"),
            "reason": rating.get("reason") or rating.get("reason_code"),
            "comment": rating.get("comment"),
            "requester_id": rating.get("requester_id"),
            "ticket_id": rating.get("ticket_id") or ticket_id,
            "created_at": rating.get("created_at"),
            "updated_at": rating.get("updated_at"),
            "url": f"{base_url}/agent/tickets/{ticket_id}",
            "raw": rating,
        },
    )


def _rating_content(*, score: str | None, reason: str | None, comment: str | None) -> str:
    parts = [f"Score: {score}" if score else ""]
    if reason:
        parts.append(f"Reason: {reason}")
    if comment:
        parts.append(comment)
    return ". ".join(part for part in parts if part) or "Satisfaction rating"


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


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
