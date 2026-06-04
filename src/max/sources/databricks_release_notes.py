"""Databricks Release Notes source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.base import SourceAdapter
from max.sources.fly_io_changelog import _parse
from max.types.signal import Signal, SignalSourceType


class DatabricksReleaseNotesAdapter(SourceAdapter):
    config_keys = ["entries", "payload", "feed_url", "products", "keywords", "timeout"]
    required_keys: list[str] = []
    description = "Ingests Databricks release notes as data platform and AI infrastructure signals."

    @property
    def name(self) -> str:
        return "databricks_release_notes"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_databricks_release_notes(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_databricks_release_notes(payload: Any) -> list[Signal]:
    signals = _parse(payload, "databricks_release_notes", "Databricks Release Notes", ("product", "release_area", "category"))
    for signal in signals:
        area = str(signal.metadata.get("release_area") or signal.metadata.get("product") or signal.metadata.get("category") or "").strip()
        signal.source_type = SignalSourceType.ROADMAP
        signal.tags = _tags(["databricks", "data-platform", "ai-infrastructure", area, *signal.tags])
        if area:
            signal.metadata["release_area"] = area
    return signals


def _tags(values: list[str]) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for value in values:
        tag = str(value).strip().lower().replace(" ", "-")
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags
