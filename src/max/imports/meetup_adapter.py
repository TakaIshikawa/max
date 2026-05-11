"""Meetup source adapter for tech event and community signals."""

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

MEETUP_API = "https://api.meetup.com"
_DEFAULT_TOPICS = ["artificial-intelligence", "developer-tools", "cloud", "data"]
_DEFAULT_LOCATIONS = ["San Francisco", "New York", "London"]


def _get_token() -> str | None:
    token = os.environ.get("MEETUP_TOKEN") or os.environ.get("MEETUP_OAUTH_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["vault", "get", "meetup/token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _parse_dt(value: str | int | float | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("html") or "")
    return str(value or "")


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value).strip()


def _tags(event: dict[str, Any], topic: str) -> list[str]:
    text = f"{event.get('title') or event.get('name')} {_text(event.get('description'))}".lower()
    tags = {topic, "meetup"}
    for tag, keywords in {
        "ai": ["ai", "llm", "machine learning", "artificial intelligence"],
        "cloud": ["cloud", "kubernetes", "serverless"],
        "devtools": ["developer", "api", "sdk", "platform engineering"],
        "data": ["data", "analytics", "database"],
        "security": ["security", "cybersecurity"],
    }.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)
    return sorted(tags)[:10]


class MeetupAdapter(SourceAdapter):
    """Fetch upcoming Meetup events by topic, location, or configured group."""

    @property
    def name(self) -> str:
        return "meetup_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def topics(self) -> list[str]:
        return self._configured_terms("topics", _DEFAULT_TOPICS)

    @property
    def locations(self) -> list[str]:
        return self._configured_terms("locations", _DEFAULT_LOCATIONS)

    @property
    def groups(self) -> list[str]:
        return self._configured_terms("groups", [])

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []
        token = _get_token()
        if not token:
            logger.warning("No Meetup OAuth token configured")
            return []

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        signals: list[Signal] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for group in self.groups:
                if len(signals) >= limit:
                    break
                await self._fetch_group_events(client, group, limit, signals, seen)
            for topic in self.topics:
                for location in self.locations:
                    if len(signals) >= limit:
                        break
                    await self._fetch_topic_events(client, topic, location, limit, signals, seen)
        return signals[:limit]

    async def _fetch_group_events(
        self,
        client: httpx.AsyncClient,
        group: str,
        limit: int,
        signals: list[Signal],
        seen: set[str],
    ) -> None:
        try:
            resp = await fetch_with_retry(
                f"{MEETUP_API}/{group}/events",
                client,
                adapter_name=self.name,
                params={"page": min(limit, 50)},
            )
            events = resp.json()
        except Exception:
            logger.warning("Meetup group fetch failed for %s", group, exc_info=True)
            return
        for event in events if isinstance(events, list) else events.get("events", []):
            self._append_event(event, topic=group, location=None, signals=signals, seen=seen, limit=limit)

    async def _fetch_topic_events(
        self,
        client: httpx.AsyncClient,
        topic: str,
        location: str,
        limit: int,
        signals: list[Signal],
        seen: set[str],
    ) -> None:
        try:
            resp = await fetch_with_retry(
                f"{MEETUP_API}/find/upcoming_events",
                client,
                adapter_name=self.name,
                params={"topic_category": topic, "location": location, "page": min(limit, 50)},
            )
            data = resp.json()
        except Exception:
            logger.warning("Meetup topic fetch failed for %s/%s", topic, location, exc_info=True)
            return
        for event in data.get("events", []) if isinstance(data, dict) else []:
            self._append_event(event, topic=topic, location=location, signals=signals, seen=seen, limit=limit)

    def _append_event(
        self,
        event: dict[str, Any],
        *,
        topic: str,
        location: str | None,
        signals: list[Signal],
        seen: set[str],
        limit: int,
    ) -> None:
        if len(signals) >= limit or not isinstance(event, dict):
            return
        event_id = str(event.get("id") or event.get("event_id") or "")
        if not event_id or event_id in seen:
            return
        seen.add(event_id)
        group = event.get("group") if isinstance(event.get("group"), dict) else {}
        venue = event.get("venue") if isinstance(event.get("venue"), dict) else {}
        rsvp_count = int(event.get("yes_rsvp_count") or event.get("rsvp_count") or 0)
        capacity = event.get("rsvp_limit") or event.get("capacity")
        title = str(event.get("title") or event.get("name") or "")
        description = _strip_html(_text(event.get("description")))
        signals.append(
            Signal(
                source_type=SignalSourceType.MARKET,
                source_adapter=self.name,
                title=title,
                content=(description or title)[:1000],
                url=str(event.get("link") or event.get("event_url") or ""),
                author=group.get("name") if isinstance(group, dict) else None,
                published_at=_parse_dt(event.get("time") or (event.get("dateTime") or "")),
                tags=_tags(event, topic),
                credibility=min(0.3 + rsvp_count / 250, 1.0),
                metadata={
                    "event_id": event_id,
                    "topic": topic,
                    "location": location,
                    "rsvp_count": rsvp_count,
                    "capacity": capacity,
                    "group": {
                        "id": group.get("id"),
                        "name": group.get("name"),
                        "urlname": group.get("urlname"),
                        "members": group.get("members"),
                    },
                    "venue": venue.get("name") if isinstance(venue, dict) else None,
                    "trending_topics": [tag for tag in _tags(event, topic) if tag not in {"meetup", topic}],
                },
            )
        )
