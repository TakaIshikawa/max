"""Google Cloud release notes source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.fly_io_changelog import _parse
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class GoogleCloudReleaseNotesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "google_cloud_release_notes"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_google_cloud_release_notes(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_google_cloud_release_notes(payload: Any) -> list[Signal]:
    return _parse(payload, "google_cloud_release_notes", "Google Cloud", ("product", "service", "release_type"))
