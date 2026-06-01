"""Pulumi blog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.prisma_releases import _parse
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class PulumiBlogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "pulumi_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_pulumi_blog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_pulumi_blog(payload: Any) -> list[Signal]:
    signals = _parse(payload, "pulumi_blog", "Pulumi", ("infrastructure", "cloud_provider", "product", "tags"))
    for signal in signals:
        signal.source_type = SignalSourceType.NEWS
    return signals
