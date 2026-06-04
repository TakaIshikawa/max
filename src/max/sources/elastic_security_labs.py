"""Elastic Security Labs source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.django_weblog import parse_configured_entries
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class ElasticSecurityLabsAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "elastic_security_labs"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        payload = self._config.get("entries") or self._config.get("payload") or []
        return parse_elastic_security_labs(payload, limit=limit)


def parse_elastic_security_labs(
    payload: Any, *, limit: int | None = None
) -> list[Signal]:
    return parse_configured_entries(
        payload,
        adapter="elastic_security_labs",
        source_name="Elastic Security Labs",
        source_type=SignalSourceType.NEWS,
        metadata_keys=(
            "threat_category",
            "malware_family",
            "cve_ids",
            "tactics",
            "tags",
        ),
        default_tags=("security", "elastic"),
        limit=limit,
    )
