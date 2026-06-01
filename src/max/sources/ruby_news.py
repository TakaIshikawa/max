"""Ruby News source adapter."""

from __future__ import annotations

import re

from max.sources.python_dev_blog import PythonDevBlogAdapter


class RubyNewsAdapter(PythonDevBlogAdapter):
    @property
    def name(self) -> str:
        return "ruby_news"

    async def fetch(self, *, limit: int = 30):
        signals = await super().fetch(limit=limit)
        for signal in signals:
            signal.tags = ["ruby", *[tag for tag in signal.tags if tag != "python"]]
            signal.metadata["category"] = signal.metadata.get("tags", [None])[0] if signal.metadata.get("tags") else None
            signal.metadata["version"] = _version(signal.title)
        return signals


def _version(title: str) -> str | None:
    match = re.search(r"\b(\d+\.\d+(?:\.\d+)?)\b", title)
    return match.group(1) if match else None
