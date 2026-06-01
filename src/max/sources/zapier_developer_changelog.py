"""Zapier developer changelog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.prisma_releases import _parse
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class ZapierDeveloperChangelogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "zapier_developer_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_zapier_developer_changelog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_zapier_developer_changelog(payload: Any) -> list[Signal]:
    return _parse(payload, "zapier_developer_changelog", "Zapier Developer", ("platform", "app", "category"))
