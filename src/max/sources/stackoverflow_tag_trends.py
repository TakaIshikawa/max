"""Stack Overflow tag trend source adapter."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.sources.stackoverflow import SE_API, _DEFAULT_TAGS, _get_api_key
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class StackOverflowTagTrendsAdapter(SourceAdapter):
    """Fetch Stack Exchange tag metadata as compact demand trend snapshots."""

    @property
    def name(self) -> str:
        return "stackoverflow_tag_trends"

    @property
    def source_type(self) -> str:
        return SignalSourceType.TRENDING.value

    @property
    def tags(self) -> list[str]:
        return self._configured_terms("tags", _DEFAULT_TAGS)

    @property
    def site(self) -> str:
        value = self._config.get("site", "stackoverflow")
        return value.strip() if isinstance(value, str) and value.strip() else "stackoverflow"

    @property
    def pagesize(self) -> int:
        return _positive_int(self._config.get("pagesize"), default=30, maximum=100)

    @property
    def fromdate(self) -> int | None:
        return _optional_positive_int(self._config.get("fromdate"))

    @property
    def todate(self) -> int | None:
        return _optional_positive_int(self._config.get("todate"))

    @property
    def timeout(self) -> float:
        value = self._config.get("timeout", 30)
        if isinstance(value, bool):
            return 30.0
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 30.0
        return parsed if parsed > 0 else 30.0

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []

        api_key = _get_api_key()
        params: dict[str, object] = {
            "site": self.site,
            "pagesize": min(self.pagesize, limit, 100),
        }
        if self.fromdate is not None:
            params["fromdate"] = self.fromdate
        if self.todate is not None:
            params["todate"] = self.todate
        if api_key:
            params["key"] = api_key

        tag_path = ";".join(quote(tag, safe="") for tag in self.tags[:100])
        if not tag_path:
            return []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await fetch_with_retry(
                    f"{SE_API}/tags/{tag_path}/info",
                    client,
                    adapter_name=self.name,
                    params=params,
                )
                data = resp.json()
        except Exception:
            logger.warning("Stack Overflow tag trend fetch failed", exc_info=True)
            return []

        items = data.get("items", [])
        if not isinstance(items, list):
            return []

        signals: list[Signal] = []
        seen_tags: set[str] = set()
        for item in items:
            signal = self._normalize_tag(item)
            if signal is None or signal.metadata["tag"] in seen_tags:
                continue
            seen_tags.add(signal.metadata["tag"])
            signals.append(signal)
            if len(signals) >= limit:
                break

        return signals

    def _normalize_tag(self, item: object) -> Signal | None:
        if not isinstance(item, dict):
            return None

        tag_name = _string_or_none(item.get("name"))
        if tag_name is None:
            return None

        count = _nonnegative_int(item.get("count"), default=0)
        last_activity = _datetime_from_epoch(item.get("last_activity_date"))
        source_url = _tag_url(site=self.site, tag=tag_name)

        title = f"Stack Overflow tag trend: {tag_name}"
        content = f"{tag_name} has {count:,} questions on {self.site}."
        if last_activity is not None:
            content += f" Last activity: {last_activity.isoformat()}."

        return Signal(
            id=f"stackoverflow_tag_trends:{self.site}:{tag_name.lower()}",
            source_type=SignalSourceType.TRENDING,
            source_adapter=self.name,
            title=title,
            content=content,
            url=source_url,
            published_at=last_activity,
            tags=_signal_tags(self.site, tag_name),
            credibility=min(count / 1_000_000, 1.0),
            metadata={
                "signal_role": "market",
                "site": self.site,
                "tag": tag_name,
                "configured_tags": self.tags,
                "question_count": count,
                "last_activity_date": item.get("last_activity_date"),
                "source_url": source_url,
                "fromdate": self.fromdate,
                "todate": self.todate,
                "has_synonyms": item.get("has_synonyms", False),
                "is_moderator_only": item.get("is_moderator_only", False),
                "is_required": item.get("is_required", False),
            },
        )


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def _optional_positive_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _nonnegative_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0)


def _datetime_from_epoch(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _tag_url(*, site: str, tag: str) -> str:
    host = "stackoverflow.com" if site == "stackoverflow" else f"{site}.stackexchange.com"
    return f"https://{host}/questions/tagged/{quote(tag, safe='')}"


def _signal_tags(site: str, tag: str) -> list[str]:
    tags = ["stackoverflow", "stackexchange", site, tag.lower()]
    deduped: list[str] = []
    for value in tags:
        if value not in deduped:
            deduped.append(value)
    return deduped
