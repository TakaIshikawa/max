"""Elastic Blog source adapter."""

from __future__ import annotations

from urllib.parse import urlparse

from max.sources.python_dev_blog import PythonDevBlogAdapter


class ElasticBlogAdapter(PythonDevBlogAdapter):
    @property
    def name(self) -> str:
        return "elastic_blog"

    async def fetch(self, *, limit: int = 30):
        signals = await super().fetch(limit=limit)
        for signal in signals:
            signal.tags = ["elastic", *[tag for tag in signal.tags if tag != "python"]]
            signal.metadata["product_area"] = _product_area(signal.url, signal.metadata.get("tags", []))
        return signals


def _product_area(url: str, tags: list[str]) -> str | None:
    for tag in tags:
        lowered = tag.lower()
        if lowered in {"elasticsearch", "kibana", "observability", "security"}:
            return lowered
    path = urlparse(url).path.lower()
    for area in ("elasticsearch", "kibana", "observability", "security"):
        if area in path:
            return area
    return None
