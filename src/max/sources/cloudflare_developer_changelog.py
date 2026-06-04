"""Cloudflare developer changelog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.base import SourceAdapter
from max.sources.fly_io_changelog import _parse
from max.types.signal import Signal, SignalSourceType


class CloudflareDeveloperChangelogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "cloudflare_developer_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_cloudflare_developer_changelog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_cloudflare_developer_changelog(payload: Any) -> list[Signal]:
    return _parse(payload, "cloudflare_developer_changelog", "Cloudflare Developer Changelog", ("product", "category"))
