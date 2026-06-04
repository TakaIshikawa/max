"""Canonical Ubuntu Security Notices source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.base import SourceAdapter
from max.sources.fly_io_changelog import _dt, _id, _text
from max.types.signal import Signal, SignalSourceType


class CanonicalUbuntuSecurityNoticesAdapter(SourceAdapter):
    config_keys = ["entries", "payload", "feed_url", "keywords", "max_age_days", "timeout"]
    required_keys: list[str] = []
    description = "Ingests Ubuntu Security Notices as vulnerability and infrastructure security signals."

    @property
    def name(self) -> str:
        return "canonical_ubuntu_security_notices"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SECURITY.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_canonical_ubuntu_security_notices(self._config.get("entries") or self._config.get("payload") or [])[:limit]


def parse_canonical_ubuntu_security_notices(payload: Any) -> list[Signal]:
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    signals: list[Signal] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        advisory_id = _text(entry.get("advisory_id") or entry.get("id") or entry.get("usn"))
        title = _text(entry.get("title") or advisory_id)
        url = _text(entry.get("url") or entry.get("link"))
        if not title or not url:
            continue
        packages = _list(entry.get("affected_packages") or entry.get("packages"))
        signals.append(
            Signal(
                id=_id("canonical_ubuntu_security_notices", url, title),
                source_type=SignalSourceType.SECURITY,
                source_adapter="canonical_ubuntu_security_notices",
                title=title,
                content=_text(entry.get("summary") or entry.get("content") or entry.get("description"))[:1000],
                url=url,
                published_at=_dt(entry.get("published_at") or entry.get("date")),
                tags=_tags(["ubuntu", "canonical", "security", *packages]),
                metadata={"advisory_id": advisory_id, "affected_packages": packages},
            )
        )
    return signals


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [part.strip() for part in text.split(",") if part.strip()] if text else []


def _tags(values: list[str]) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for value in values:
        tag = _text(value).lower().replace(" ", "-")
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags
