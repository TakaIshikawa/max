"""Tailscale Changelog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.base import SourceAdapter
from max.sources.fly_io_changelog import _parse
from max.types.signal import Signal, SignalSourceType


class TailscaleChangelogAdapter(SourceAdapter):
    config_keys = ["entries", "payload", "feed_url", "products", "keywords", "timeout"]
    required_keys: list[str] = []
    description = "Ingests Tailscale changelog entries as networking infrastructure signals."

    @property
    def name(self) -> str:
        return "tailscale_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_tailscale_changelog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_tailscale_changelog(payload: Any) -> list[Signal]:
    signals = _parse(payload, "tailscale_changelog", "Tailscale Changelog", ("category", "platform"))
    for signal in signals:
        signal.source_type = SignalSourceType.ROADMAP
        signal.tags = _tags(["tailscale", "networking", "infrastructure", *signal.tags])
    return signals


def _tags(values: list[str]) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for value in values:
        tag = str(value).strip().lower().replace(" ", "-")
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags
