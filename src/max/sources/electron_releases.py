"""Electron Releases source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.django_weblog import parse_configured_entries
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class ElectronReleasesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "electron_releases"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        payload = self._config.get("entries") or self._config.get("payload") or []
        return parse_electron_releases(payload, limit=limit)


def parse_electron_releases(payload: Any, *, limit: int | None = None) -> list[Signal]:
    return parse_configured_entries(
        payload,
        adapter="electron_releases",
        source_name="Electron Releases",
        source_type=SignalSourceType.ROADMAP,
        metadata_keys=("version", "channel", "breaking_changes", "platform"),
        default_tags=("electron",),
        limit=limit,
    )
