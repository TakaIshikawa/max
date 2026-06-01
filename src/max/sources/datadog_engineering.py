"""Datadog Engineering Blog source adapter."""

from __future__ import annotations

from max.sources.python_dev_blog import PythonDevBlogAdapter


class DatadogEngineeringAdapter(PythonDevBlogAdapter):
    @property
    def name(self) -> str:
        return "datadog_engineering"

    async def fetch(self, *, limit: int = 30):
        signals = await super().fetch(limit=limit)
        for signal in signals:
            normalized_tags = sorted({tag.lower() for tag in signal.metadata.get("tags", []) if tag})
            signal.tags = ["datadog", *normalized_tags]
            signal.metadata["tags"] = normalized_tags
        return signals
