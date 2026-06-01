"""GitHub Blog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.fly_io_changelog import _parse
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class GitHubBlogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "github_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ARTICLE.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_github_blog(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_github_blog(payload: Any) -> list[Signal]:
    signals = _parse(payload, "github_blog", "GitHub Blog", ("category", "author"))
    for signal in signals:
        signal.source_type = SignalSourceType.ARTICLE
        if signal.metadata.get("author"):
            signal.author = str(signal.metadata["author"])
    return signals
