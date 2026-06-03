"""Google Workspace developer changelog source adapter."""

from __future__ import annotations

from typing import Any

from max.sources.base import SourceAdapter
from max.sources.twilio_changelog import _fetch_text, _parse, text as _text
from max.types.signal import Signal, SignalSourceType

DEFAULT_FEED_URL = "https://developers.google.com/workspace/updates/rss.xml"


class GoogleWorkspaceDeveloperChangelogAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "google_workspace_developer_changelog"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        try:
            payload = self._config.get("entries") or self._config.get("payload")
            if payload is None:
                payload = await _fetch_text(_text(self._config.get("feed_url")) or DEFAULT_FEED_URL, float(self._config.get("timeout", 10)))
            return parse_google_workspace_developer_changelog(
                payload,
                feed_url=_text(self._config.get("feed_url")) or DEFAULT_FEED_URL,
                products=self._config.get("products"),
                keywords=self._config.get("keywords"),
                max_age_days=self._config.get("max_age_days"),
            )[:limit]
        except Exception:
            return []


def parse_google_workspace_developer_changelog(
    payload: Any,
    *,
    feed_url: str = DEFAULT_FEED_URL,
    products: Any = None,
    keywords: Any = None,
    max_age_days: Any = None,
) -> list[Signal]:
    signals = _parse(
        payload,
        "google_workspace_developer_changelog",
        "google-workspace",
        feed_url,
        products,
        keywords,
        max_age_days,
    )
    for signal in signals:
        signal.source_type = SignalSourceType.NEWS
    return signals
