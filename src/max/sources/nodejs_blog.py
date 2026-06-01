"""Node.js Blog source adapter."""

from __future__ import annotations

import re

from max.sources.python_dev_blog import PythonDevBlogAdapter


class NodejsBlogAdapter(PythonDevBlogAdapter):
    @property
    def name(self) -> str:
        return "nodejs_blog"

    async def fetch(self, *, limit: int = 30):
        signals = await super().fetch(limit=limit)
        for signal in signals:
            signal.tags = ["nodejs", *[tag for tag in signal.tags if tag != "python"]]
            version = _version(signal.title)
            signal.metadata["version"] = version
            signal.metadata["release_line"] = _release_line(version)
        return signals


def _version(title: str) -> str | None:
    match = re.search(r"\bv?(\d+\.\d+\.\d+)\b", title)
    return match.group(1) if match else None


def _release_line(version: str | None) -> str | None:
    if not version:
        return None
    parts = version.split(".")
    return f"{parts[0]}.x" if parts else None
