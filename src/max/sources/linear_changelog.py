"""Linear changelog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.prisma_releases import _parse
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class LinearChangelogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "linear_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_linear_changelog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_linear_changelog(payload: Any) -> list[Signal]:
    return _parse(payload, "linear_changelog", "Linear", ("feature_category", "category"))
