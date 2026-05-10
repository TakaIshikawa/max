"""Discord source adapter — community signals from developer servers."""

from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"
_DEFAULT_BOT_TOKEN_ENV = "DISCORD_BOT_TOKEN"

_KEYWORD_TAGS = {
    "ai": ["ai", "llm", "gpt", "claude", "openai", "anthropic"],
    "agent": ["agent", "agentic", "autonomous"],
    "mcp": ["mcp", "model context protocol"],
    "rust": ["rust", "cargo"],
    "python": ["python", "pip"],
    "security": ["security", "vulnerability", "cve"],
    "open_source": ["open source", "oss", "foss"],
    "devtools": ["devtools", "developer tools", "tooling"],
}


class DiscordAdapter(SourceAdapter):
    """Fetch messages from Discord channels to capture community feedback and discussions."""

    @property
    def name(self) -> str:
        return "discord"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FORUM.value

    @property
    def channel_ids(self) -> list[str]:
        return _normalize_ids(self._config.get("channel_ids", []))

    @property
    def guild_ids(self) -> list[str]:
        return _normalize_ids(self._config.get("guild_ids", []))

    @property
    def bot_token_env(self) -> str:
        value = self._config.get("bot_token_env", _DEFAULT_BOT_TOKEN_ENV)
        return value if isinstance(value, str) and value.strip() else _DEFAULT_BOT_TOKEN_ENV

    @property
    def min_reactions(self) -> int:
        return _int_or_zero(self._config.get("min_reactions"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        token = os.environ.get(self.bot_token_env)
        if not token:
            logger.warning("Discord bot token not found in env var %s", self.bot_token_env)
            return []

        headers = {
            "Authorization": f"Bot {token}",
            "User-Agent": "max-discord-adapter/0.1",
            "Accept": "application/json",
        }

        signals: list[Signal] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(
            timeout=30, headers=headers, follow_redirects=True,
        ) as client:
            # Fetch from explicit channel IDs
            for channel_id in self.channel_ids:
                if len(signals) >= limit:
                    break
                await self._fetch_channel_messages(
                    client, channel_id=channel_id, signals=signals,
                    seen_ids=seen_ids, limit=limit,
                )

            # Fetch channels from guild IDs, then messages
            for guild_id in self.guild_ids:
                if len(signals) >= limit:
                    break
                await self._fetch_guild_channels(
                    client, guild_id=guild_id, signals=signals,
                    seen_ids=seen_ids, limit=limit,
                )

        return signals[:limit]

    async def _fetch_guild_channels(
        self,
        client: httpx.AsyncClient,
        *,
        guild_id: str,
        signals: list[Signal],
        seen_ids: set[str],
        limit: int,
    ) -> None:
        try:
            resp = await fetch_with_retry(
                f"{DISCORD_API_BASE}/guilds/{guild_id}/channels",
                client,
                adapter_name=self.name,
            )
            channels = resp.json()
        except (AdapterFetchError, httpx.RequestError, httpx.TimeoutException, ValueError):
            logger.warning("Discord guild channels fetch failed for %s", guild_id, exc_info=True)
            return

        if not isinstance(channels, list):
            return

        # Filter to text channels (type 0) and forum channels (type 15)
        text_channels = [
            ch for ch in channels
            if isinstance(ch, dict) and ch.get("type") in (0, 15)
        ]

        for channel in text_channels:
            if len(signals) >= limit:
                break
            channel_id = channel.get("id")
            if not channel_id:
                continue
            await self._fetch_channel_messages(
                client, channel_id=str(channel_id), signals=signals,
                seen_ids=seen_ids, limit=limit,
                guild_id=guild_id, channel_name=channel.get("name"),
            )

    async def _fetch_channel_messages(
        self,
        client: httpx.AsyncClient,
        *,
        channel_id: str,
        signals: list[Signal],
        seen_ids: set[str],
        limit: int,
        guild_id: str | None = None,
        channel_name: str | None = None,
    ) -> None:
        per_channel = min(max(limit - len(signals), 5), 100)
        try:
            resp = await fetch_with_retry(
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                client,
                adapter_name=self.name,
                params={"limit": per_channel},
            )
            messages = resp.json()
        except (AdapterFetchError, httpx.RequestError, httpx.TimeoutException, ValueError):
            logger.warning(
                "Discord message fetch failed for channel %s", channel_id, exc_info=True,
            )
            return

        if not isinstance(messages, list):
            return

        for msg in messages:
            if len(signals) >= limit:
                break
            if not isinstance(msg, dict):
                continue

            msg_id = msg.get("id")
            if not msg_id or str(msg_id) in seen_ids:
                continue

            signal = self._message_to_signal(
                msg, channel_id=channel_id, guild_id=guild_id,
                channel_name=channel_name,
            )
            if signal is None:
                continue

            seen_ids.add(str(msg_id))
            signals.append(signal)

    def _message_to_signal(
        self,
        msg: dict,
        *,
        channel_id: str,
        guild_id: str | None = None,
        channel_name: str | None = None,
    ) -> Signal | None:
        # Skip bot messages
        author = msg.get("author", {})
        if isinstance(author, dict) and author.get("bot"):
            return None

        content = msg.get("content", "")
        if not content or not isinstance(content, str):
            return None

        # Count reactions
        reactions = msg.get("reactions", [])
        total_reactions = _count_reactions(reactions)
        if total_reactions < self.min_reactions:
            return None

        msg_id = str(msg.get("id", ""))
        timestamp = _parse_discord_timestamp(msg.get("timestamp"))
        author_name = _author_display(author)
        thread = msg.get("thread")
        has_thread = isinstance(thread, dict) and thread.get("id") is not None

        return Signal(
            source_type=SignalSourceType.FORUM,
            source_adapter=self.name,
            title=_title_from_content(content),
            content=content[:1000],
            url=_message_url(guild_id=guild_id, channel_id=channel_id, message_id=msg_id),
            author=author_name,
            published_at=timestamp,
            tags=_extract_tags(content, channel_name),
            credibility=_credibility(total_reactions=total_reactions, has_thread=has_thread),
            metadata={
                "channel_id": channel_id,
                "guild_id": guild_id,
                "channel_name": channel_name,
                "message_id": msg_id,
                "author_id": author.get("id") if isinstance(author, dict) else None,
                "reactions": total_reactions,
                "has_thread": has_thread,
                "thread_id": thread.get("id") if isinstance(thread, dict) else None,
                "mentions": len(msg.get("mentions", [])),
                "attachments": len(msg.get("attachments", [])),
            },
        )


def _normalize_ids(values: object) -> list[str]:
    if not isinstance(values, list):
        values = [values]
    result: list[str] = []
    seen: set[str] = set()
    for v in values:
        if not isinstance(v, (str, int)) or isinstance(v, bool):
            continue
        s = str(v).strip()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _int_or_zero(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _parse_discord_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _count_reactions(reactions: object) -> int:
    if not isinstance(reactions, list):
        return 0
    total = 0
    for r in reactions:
        if isinstance(r, dict):
            total += _int_or_zero(r.get("count"))
    return total


def _author_display(author: object) -> str | None:
    if not isinstance(author, dict):
        return None
    display = author.get("global_name") or author.get("username")
    return str(display) if display else None


def _message_url(
    *, guild_id: str | None, channel_id: str, message_id: str,
) -> str:
    if guild_id:
        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    return f"https://discord.com/channels/@me/{channel_id}/{message_id}"


def _title_from_content(content: str) -> str:
    line = " ".join(content.split())
    return line[:117] + "..." if len(line) > 120 else line


def _extract_tags(content: str, channel_name: str | None) -> list[str]:
    tags: set[str] = {"discord"}
    lower = content.lower()

    if channel_name:
        tags.add(channel_name.replace("-", "_"))

    for tag, keywords in _KEYWORD_TAGS.items():
        if any(kw in lower for kw in keywords):
            tags.add(tag)

    return sorted(tags)[:10]


def _credibility(*, total_reactions: int, has_thread: bool) -> float:
    score = total_reactions * 2
    if has_thread:
        score += 10
    return min(0.2 + (score / 100.0), 1.0)
