"""Semgrep blog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.base import SourceAdapter
from max.sources.fly_io_changelog import _parse
from max.types.signal import Signal, SignalSourceType


class SemgrepBlogAdapter(SourceAdapter):
    config_keys = ["entries", "payload", "feed_url", "keywords", "max_age_days", "timeout"]
    required_keys: list[str] = []
    description = "Ingests Semgrep blog posts as application security and developer tooling signals."

    @property
    def name(self) -> str:
        return "semgrep_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_semgrep_blog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_semgrep_blog(payload: Any) -> list[Signal]:
    signals = _parse(payload, "semgrep_blog", "Semgrep Blog", ("category", "tag"))
    for signal in signals:
        signal.source_type = SignalSourceType.SECURITY
        signal.tags = _tags(["semgrep", "application-security", "devtools", *signal.tags])
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
