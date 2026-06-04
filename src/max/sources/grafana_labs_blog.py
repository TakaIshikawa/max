"""Grafana Labs Blog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.django_weblog import parse_configured_entries
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class GrafanaLabsBlogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "grafana_labs_blog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ARTICLE.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        payload = self._config.get("entries") or self._config.get("payload") or []
        return parse_grafana_labs_blog(payload, limit=limit)


def parse_grafana_labs_blog(payload: Any, *, limit: int | None = None) -> list[Signal]:
    return parse_configured_entries(
        payload,
        adapter="grafana_labs_blog",
        source_name="Grafana Labs Blog",
        source_type=SignalSourceType.ARTICLE,
        metadata_keys=("product", "topic", "tags", "author"),
        default_tags=("grafana",),
        limit=limit,
    )
