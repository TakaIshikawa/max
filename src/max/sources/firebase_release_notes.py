"""Firebase release notes source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.base import SourceAdapter
from max.sources.prisma_releases import _parse
from max.types.signal import Signal, SignalSourceType


class FirebaseReleaseNotesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "firebase_release_notes"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_firebase_release_notes(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_firebase_release_notes(payload: Any) -> list[Signal]:
    return _parse(payload, "firebase_release_notes", "Firebase Release Notes", ("product", "platform", "release_note_type"))
