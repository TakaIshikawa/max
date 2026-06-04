"""Atlassian Developer Changelog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.base import SourceAdapter
from max.sources.fly_io_changelog import _parse
from max.types.signal import Signal, SignalSourceType


class AtlassianDeveloperChangelogAdapter(SourceAdapter):
    config_keys = ["entries", "payload", "feed_url", "products", "keywords", "timeout"]
    required_keys: list[str] = []
    description = "Ingests Atlassian developer changelog items for Jira, Confluence, and platform signals."

    @property
    def name(self) -> str:
        return "atlassian_developer_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_atlassian_developer_changelog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_atlassian_developer_changelog(payload: Any) -> list[Signal]:
    signals = _parse(payload, "atlassian_developer_changelog", "Atlassian Developer Changelog", ("product", "category"))
    for signal in signals:
        product = str(signal.metadata.get("product") or signal.metadata.get("category") or "").strip()
        signal.source_type = SignalSourceType.ROADMAP
        signal.tags = _tags(["atlassian", "developer-platform", product, *signal.tags])
        if product:
            signal.metadata["product_area"] = product
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
