"""Heroku changelog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.fly_io_changelog import _parse
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class HerokuChangelogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "heroku_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_heroku_changelog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_heroku_changelog(payload: Any) -> list[Signal]:
    return _parse(payload, "heroku_changelog", "Heroku", ("category", "runtime", "product_area"))
