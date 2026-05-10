"""Discord source adapter — community insights from developer servers."""

from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"

_DEFAULT_BOT_TOKEN_ENV = "DISCORD_BOT_TOKEN"

_KEYWORD_TAGS: dict[str, str] = {
    "agent": "agent",
    "llm": "llm",
    "mcp": "mcp",
    "openai": "openai",
    "langchain": "langchain",
    "rag": "rag",
    "embedding": "embedding",
    "claude": "claude",
    "anthropic": "anthropic",
    "bug": "bug",
    "feature": "feature-request",
}


def _extract_tags(text: str, channel_name: str | None) -> list[str]:
    """Build signal tags from message text and channel context."""
    tags: set[str] = {"discord"}

    if channel_name:
        tag = channel_name.strip().lower().replace(" ", "-")[:30]
        if tag:
            tags.add(tag)

    text_lower = text.lower()
    for keyword, tag in _KEYWORD_TAGS.items():
        if keyword in text_lower:
            tags.add(tag)

    return sorted(tags)[:10]


def _parse_datetime(date_str: str | None) -> datetime | None:
    """Parse ISO 8601 datetime from Discord API."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _title_from_content(text: str) -> str:
    """Create a title from message content."""
    title = " ".join(text.split())
    if len(title) <= 100:
        return title
    return f"{title[:97].rstrip()}..."


def _reaction_credibility(reaction_count: int) -> float:
    """Compute credibility score from reaction count."""
    return min(round(0.2 + (reaction_count / 50), 3), 1.0)


class DiscordAdapter(SourceAdapter):
    """Fetch messages from specified Discord channels and servers."""

    @property
    def name(self) -> str:
        return "discord"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def channel_ids(self) -> list[str]:
        raw = self._config.get("channel_ids", [])
        if isinstance(raw, list):
            return [str(c).strip() for c in raw if str(c).strip()]
        return []

    @property
    def bot_token_env(self) -> str:
        return self._config.get("bot_token_env", _DEFAULT_BOT_TOKEN_ENV)

    @property
    def messages_per_channel(self) -> int:
        return min(self._config.get("messages_per_channel", 50), 100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        bot_token = os.environ.get(self.bot_token_env, "")
        if not bot_token:
            logger.warning(
                "%s: no bot token found in env var %s",
                self.name, self.bot_token_env,
            )
            return []

        channel_ids = self.channel_ids
        if not channel_ids:
            logger.warning("%s: no channel_ids configured", self.name)
            return []

        signals: list[Signal] = []
        seen_ids: set[str] = set()

        headers = {
            "Authorization": f"Bot {bot_token}",
            "User-Agent": "max-discord-adapter/0.1",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for channel_id in channel_ids:
                if len(signals) >= limit:
                    break

                messages = await self._fetch_channel_messages(
                    client,
                    channel_id=channel_id,
                    msg_limit=self.messages_per_channel,
                )
                if messages is None:
                    continue

                channel_name = await self._get_channel_name(client, channel_id)

                for msg in messages:
                    if len(signals) >= limit:
                        break

                    msg_id = msg.get("id")
                    if not msg_id or msg_id in seen_ids:
                        continue
                    seen_ids.add(msg_id)

                    content = msg.get("content", "")
                    if not content:
                        continue

                    author = msg.get("author", {})
                    author_name = author.get("username") if isinstance(author, dict) else None

                    reactions = msg.get("reactions", [])
                    reaction_count = sum(
                        r.get("count", 0) for r in reactions if isinstance(r, dict)
                    ) if isinstance(reactions, list) else 0

                    signals.append(Signal(
                        source_type=SignalSourceType.FORUM,
                        source_adapter=self.name,
                        title=_title_from_content(content),
                        content=content[:1000],
                        url=f"https://discord.com/channels/-/{channel_id}/{msg_id}",
                        author=author_name,
                        published_at=_parse_datetime(msg.get("timestamp")),
                        tags=_extract_tags(content, channel_name),
                        credibility=_reaction_credibility(reaction_count),
                        metadata={
                            "message_id": msg_id,
                            "channel_id": channel_id,
                            "channel_name": channel_name,
                            "author_id": author.get("id") if isinstance(author, dict) else None,
                            "reaction_count": reaction_count,
                            "has_thread": msg.get("thread") is not None,
                        },
                    ))

        return signals[:limit]

    async def _fetch_channel_messages(
        self,
        client: httpx.AsyncClient,
        *,
        channel_id: str,
        msg_limit: int,
    ) -> list[dict] | None:
        """Fetch messages from a Discord channel."""
        try:
            resp = await fetch_with_retry(
                f"{DISCORD_API}/channels/{channel_id}/messages",
                client,
                adapter_name=self.name,
                params={"limit": msg_limit},
            )
            data = resp.json()
        except Exception:
            logger.warning(
                "%s: failed to fetch messages for channel %s",
                self.name, channel_id, exc_info=True,
            )
            return None

        if not isinstance(data, list):
            return None
        return [m for m in data if isinstance(m, dict)]

    async def _get_channel_name(
        self,
        client: httpx.AsyncClient,
        channel_id: str,
    ) -> str | None:
        """Get channel name for context tags."""
        try:
            resp = await fetch_with_retry(
                f"{DISCORD_API}/channels/{channel_id}",
                client,
                adapter_name=self.name,
            )
            data = resp.json()
        except Exception:
            return None

        if isinstance(data, dict):
            return data.get("name")
        return None
