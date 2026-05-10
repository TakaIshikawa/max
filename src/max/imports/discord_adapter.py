"""Discord source adapter — community insights from developer servers."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"

_DEFAULT_CHANNELS: list[str] = []


class DiscordAdapter(SourceAdapter):
    """Collects signals from Discord developer community servers.

    Fetches messages, reactions, and channel activity to capture community
    feedback, feature requests, and technical discussions.
    """

    @property
    def name(self) -> str:
        return "discord"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def channels(self) -> list[str]:
        return self._configured_terms("channels", _DEFAULT_CHANNELS)

    @property
    def _bot_token(self) -> str | None:
        return self._config.get("bot_token")

    @property
    def _api_base(self) -> str:
        return self._config.get("api_base", DISCORD_API_BASE)

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._bot_token:
            headers["Authorization"] = f"Bot {self._bot_token}"
        return headers

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        channels = self.channels
        if not channels:
            return signals

        per_channel = max(limit // len(channels), 5)

        async with httpx.AsyncClient(
            timeout=30,
            headers=self._auth_headers(),
            follow_redirects=True,
        ) as client:
            for channel_id in channels:
                if len(signals) >= limit:
                    break
                try:
                    resp = await fetch_with_retry(
                        f"{self._api_base}/channels/{channel_id}/messages",
                        client,
                        adapter_name=self.name,
                        params={"limit": per_channel},
                    )
                    data = resp.json()
                except AdapterFetchError:
                    logger.warning(
                        "Discord fetch failed for channel=%s", channel_id, exc_info=True,
                    )
                    continue
                except (ValueError, KeyError, TypeError):
                    logger.warning(
                        "Discord parse failed for channel=%s", channel_id, exc_info=True,
                    )
                    continue

                if not isinstance(data, list):
                    continue

                for message in data:
                    content = message.get("content", "")
                    if not content:
                        continue

                    author_info = message.get("author", {})
                    author_name = author_info.get("username") if isinstance(author_info, dict) else None

                    reactions = message.get("reactions", [])
                    reaction_count = sum(
                        _safe_int(r.get("count", 0))
                        for r in reactions
                        if isinstance(r, dict)
                    )

                    published_at = _parse_iso(message.get("timestamp"))
                    msg_id = message.get("id", "")

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.FORUM,
                            source_adapter=self.name,
                            title=content[:120],
                            content=content[:1000],
                            url=f"https://discord.com/channels/-/{channel_id}/{msg_id}" if msg_id else "",
                            author=author_name,
                            published_at=published_at,
                            tags=_extract_tags(content),
                            credibility=min(reaction_count / 50, 1.0),
                            metadata={
                                "message_id": msg_id,
                                "channel_id": channel_id,
                                "reaction_count": reaction_count,
                                "has_thread": message.get("thread") is not None,
                                "referenced_message": message.get("referenced_message") is not None,
                            },
                        )
                    )

        return signals[:limit]


def _safe_int(value: object) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_tags(text: str) -> list[str]:
    tags: list[str] = ["discord"]
    lower = text.lower()

    tech_keywords = {
        "ai": ["ai", "llm", "gpt", "machine learning"],
        "mcp": ["mcp", "model context protocol"],
        "bug": ["bug", "error", "crash", "issue"],
        "feature-request": ["feature request", "would be nice", "suggestion"],
        "help": ["help", "how do i", "question"],
    }
    for tag, terms in tech_keywords.items():
        if any(t in lower for t in terms) and tag not in tags:
            tags.append(tag)

    return tags
