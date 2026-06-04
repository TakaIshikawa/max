"""Docker Desktop Release Notes source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.django_weblog import parse_configured_entries
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class DockerDesktopReleaseNotesAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "docker_desktop_release_notes"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        payload = self._config.get("entries") or self._config.get("payload") or []
        return parse_docker_desktop_release_notes(payload, limit=limit)


def parse_docker_desktop_release_notes(
    payload: Any, *, limit: int | None = None
) -> list[Signal]:
    return parse_configured_entries(
        payload,
        adapter="docker_desktop_release_notes",
        source_name="Docker Desktop Release Notes",
        source_type=SignalSourceType.ROADMAP,
        metadata_keys=("version", "platform", "channel", "component"),
        default_tags=("docker", "desktop"),
        limit=limit,
    )
