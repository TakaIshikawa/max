"""Bun blog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.prisma_releases import _parse
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class BunBlogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "bun_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_bun_blog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_bun_blog(payload: Any) -> list[Signal]:
    signals = _parse(payload, "bun_blog", "Bun", ("version", "release", "channel"))
    for signal in signals:
        signal.source_type = SignalSourceType.NEWS
    signals.sort(key=lambda signal: (0 if signal.metadata.get("version") else 1, signal.title, signal.id))
    return signals
