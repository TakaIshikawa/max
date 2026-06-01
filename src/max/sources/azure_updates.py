"""Azure Updates source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.fly_io_changelog import _parse
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class AzureUpdatesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "azure_updates"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_azure_updates(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_azure_updates(payload: Any) -> list[Signal]:
    return _parse(payload, "azure_updates", "Azure Updates", ("category", "service", "status", "update_type"))
