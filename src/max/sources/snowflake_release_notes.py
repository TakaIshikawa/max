"""Snowflake release notes source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.prisma_releases import _parse
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class SnowflakeReleaseNotesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "snowflake_release_notes"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        client = self._config.get("client")
        if client is not None:
            try:
                payload = client.fetch_release_notes()
            except Exception:
                return []
        else:
            payload = self._config.get("entries") or self._config.get("payload") or []
        return parse_snowflake_release_notes(payload)[:limit]


def parse_snowflake_release_notes(payload: Any) -> list[Signal]:
    return _parse(payload, "snowflake_release_notes", "Snowflake", ("product_area", "product", "release_type"))
