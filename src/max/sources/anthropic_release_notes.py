"""Anthropic release notes source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.base import SourceAdapter
from max.sources.prisma_releases import _parse
from max.types.signal import Signal, SignalSourceType


class AnthropicReleaseNotesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "anthropic_release_notes"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_anthropic_release_notes(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_anthropic_release_notes(payload: Any) -> list[Signal]:
    return _parse(payload, "anthropic_release_notes", "Anthropic Release Notes", ("model", "product", "category"))
