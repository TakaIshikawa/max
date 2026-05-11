"""Eventbrite source adapter for conference and workshop signals.

Collects technology event data via the Eventbrite API. Fetches events by
category and location, extracts capacity, pricing, format, category, and
speaker signals, and follows paginated responses.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

EVENTBRITE_API = "https://www.eventbriteapi.com/v3"

_DEFAULT_CATEGORIES = ["102", "101"]  # Science & Technology, Business & Professional
_DEFAULT_LOCATIONS = ["San Francisco", "New York", "London"]
_TECH_TOPIC_KEYWORDS = {
    "ai": ["ai", "artificial intelligence", "llm", "machine learning", "generative"],
    "cloud": ["cloud", "kubernetes", "serverless", "aws", "gcp", "azure"],
    "security": ["security", "cybersecurity", "zero trust", "vulnerability"],
    "data": ["data", "analytics", "warehouse", "lakehouse", "database"],
    "devtools": ["developer", "devtools", "api", "sdk", "platform engineering"],
    "workshop": ["workshop", "hands-on", "training", "bootcamp"],
    "conference": ["conference", "summit", "expo", "forum"],
}


def _get_token() -> str | None:
    """Resolve Eventbrite OAuth token from env or vault."""
    token = os.environ.get("EVENTBRITE_TOKEN") or os.environ.get("EVENTBRITE_OAUTH_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["vault", "get", "eventbrite/token"],
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
    """Parse Eventbrite datetime strings."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _text_value(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("html") or "")
    return str(value or "")


def _event_name(event: dict[str, Any]) -> str:
    return _text_value(event.get("name")).strip()


def _event_description(event: dict[str, Any]) -> str:
    return _text_value(event.get("description")).strip()


def _event_url(event: dict[str, Any]) -> str:
    return str(event.get("url") or f"https://www.eventbrite.com/e/{event.get('id', '')}")


def _extract_capacity(event: dict[str, Any]) -> int | None:
    for key in ("capacity", "listed_capacity"):
        value = event.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    ticket_availability = event.get("ticket_availability")
    if isinstance(ticket_availability, dict):
        value = ticket_availability.get("maximum_ticket_quantity")
        if isinstance(value, int):
            return value
    return None


def _extract_pricing(event: dict[str, Any]) -> dict[str, Any]:
    ticket_classes = event.get("ticket_classes")
    costs: list[float] = []
    currencies: set[str] = set()

    if isinstance(ticket_classes, list):
        for ticket in ticket_classes:
            if not isinstance(ticket, dict):
                continue
            cost = ticket.get("cost") or ticket.get("actual_cost")
            if isinstance(cost, dict):
                currency = cost.get("currency")
                if currency:
                    currencies.add(str(currency))
                value = cost.get("major_value")
                try:
                    costs.append(float(value))
                except (TypeError, ValueError):
                    pass

    if event.get("is_free") is True:
        return {"is_free": True, "min_price": 0.0, "max_price": 0.0, "currency": None}

    return {
        "is_free": bool(event.get("is_free")) if event.get("is_free") is not None else not costs,
        "min_price": min(costs) if costs else None,
        "max_price": max(costs) if costs else None,
        "currency": sorted(currencies)[0] if currencies else None,
    }


def _extract_format(event: dict[str, Any]) -> str:
    online_event = event.get("online_event")
    if online_event is True:
        return "online"
    venue = event.get("venue")
    if isinstance(venue, dict):
        address = venue.get("address")
        if isinstance(address, dict) and address:
            return "in_person"
    if event.get("format"):
        fmt = event["format"]
        if isinstance(fmt, dict):
            return str(fmt.get("short_name") or fmt.get("name") or "unknown").lower()
    return "hybrid" if online_event is None else "in_person"


def _extract_speakers(event: dict[str, Any]) -> list[str]:
    speakers: list[str] = []
    for key in ("speakers", "presenters", "organizers"):
        values = event.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict):
                name = item.get("name") or item.get("display_name")
            else:
                name = item
            if name and str(name) not in speakers:
                speakers.append(str(name))
    return speakers[:10]


def _extract_topics(event: dict[str, Any], category: str) -> list[str]:
    text = f"{_event_name(event)} {_event_description(event)}".lower()
    topics = {category, "eventbrite"}
    for topic, keywords in _TECH_TOPIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            topics.add(topic)
    return sorted(topics)[:10]


def _credibility(capacity: int | None, pricing: dict[str, Any], speakers: list[str]) -> float:
    score = 0.35
    if capacity:
        score += min(capacity / 1000, 0.35)
    if pricing.get("min_price") not in (None, 0.0):
        score += 0.1
    if speakers:
        score += min(len(speakers) * 0.03, 0.15)
    return min(score, 1.0)


class EventbriteAdapter(SourceAdapter):
    """Fetch conference and workshop events from Eventbrite."""

    @property
    def name(self) -> str:
        return "eventbrite_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def categories(self) -> list[str]:
        return self._configured_terms("categories", _DEFAULT_CATEGORIES)

    @property
    def locations(self) -> list[str]:
        return self._configured_terms("locations", _DEFAULT_LOCATIONS)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        token = _get_token()
        if not token:
            logger.warning("No Eventbrite OAuth token configured")
            return []

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        signals: list[Signal] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for category in self.categories:
                for location in self.locations:
                    if len(signals) >= limit:
                        break
                    await self._fetch_events_page_set(
                        client,
                        category=category,
                        location=location,
                        limit=limit,
                        signals=signals,
                        seen=seen,
                    )

        return signals[:limit]

    async def _fetch_events_page_set(
        self,
        client: httpx.AsyncClient,
        *,
        category: str,
        location: str,
        limit: int,
        signals: list[Signal],
        seen: set[str],
    ) -> None:
        page = 1
        while len(signals) < limit:
            params = {
                "categories": category,
                "location.address": location,
                "expand": "venue,organizer,ticket_classes,category,format",
                "page": page,
                "sort_by": "date",
            }
            try:
                resp = await fetch_with_retry(
                    f"{EVENTBRITE_API}/events/search/",
                    client,
                    adapter_name=self.name,
                    params=params,
                )
                data = resp.json()
            except Exception:
                logger.warning(
                    "Eventbrite fetch failed for category=%s location=%s page=%s",
                    category,
                    location,
                    page,
                    exc_info=True,
                )
                return

            for event in data.get("events", []):
                if len(signals) >= limit:
                    break
                if not isinstance(event, dict):
                    continue
                event_id = str(event.get("id") or "")
                if not event_id or event_id in seen:
                    continue
                seen.add(event_id)
                signals.append(self._event_to_signal(event, category=category, location=location))

            pagination = data.get("pagination") or {}
            if not pagination.get("has_more_items") or not pagination.get("continuation"):
                break
            page += 1

    def _event_to_signal(self, event: dict[str, Any], *, category: str, location: str) -> Signal:
        title = _event_name(event)
        description = _event_description(event)
        capacity = _extract_capacity(event)
        pricing = _extract_pricing(event)
        speakers = _extract_speakers(event)
        organizer = event.get("organizer") if isinstance(event.get("organizer"), dict) else {}
        category_obj = event.get("category") if isinstance(event.get("category"), dict) else {}
        venue = event.get("venue") if isinstance(event.get("venue"), dict) else {}

        return Signal(
            source_type=SignalSourceType.MARKET,
            source_adapter=self.name,
            title=title,
            content=(description or title)[:1000],
            url=_event_url(event),
            author=organizer.get("name") if isinstance(organizer, dict) else None,
            published_at=_parse_dt((event.get("start") or {}).get("utc")),
            tags=_extract_topics(event, category),
            credibility=_credibility(capacity, pricing, speakers),
            metadata={
                "event_id": str(event.get("id") or ""),
                "category": category,
                "category_name": category_obj.get("name") if isinstance(category_obj, dict) else None,
                "location": location,
                "venue": venue.get("name") if isinstance(venue, dict) else None,
                "capacity": capacity,
                "pricing": pricing,
                "format": _extract_format(event),
                "speakers": speakers,
                "speaker_trends": _speaker_trends(speakers),
                "organizer_id": organizer.get("id") if isinstance(organizer, dict) else None,
                "status": event.get("status"),
                "online_event": event.get("online_event"),
                "ticket_sales": {
                    "has_available_tickets": (event.get("ticket_availability") or {}).get(
                        "has_available_tickets"
                    )
                    if isinstance(event.get("ticket_availability"), dict)
                    else None
                },
            },
        )


def _speaker_trends(speakers: list[str]) -> list[str]:
    trends: list[str] = []
    for speaker in speakers:
        words = re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", speaker.lower())
        trends.extend(word for word in words if word not in {"the", "and", "from"})
    return sorted(set(trends))[:10]
