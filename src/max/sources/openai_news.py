"""OpenAI News source adapter."""

from __future__ import annotations

import re
from typing import Any

from max.sources.cloudflare_blog import _canonical_url, _dt, _id, _text
from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class OpenAINewsAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "openai_news"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        return parse_openai_news(self._config.get("entries") or self._config.get("payload") or [], limit=limit)


def parse_openai_news(payload: Any, *, limit: int | None = None) -> list[Signal]:
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    signals: list[Signal] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get("title") or entry.get("headline"))
        url = _canonical_url(entry.get("url") or entry.get("link"))
        if not title or not url or url in seen:
            continue
        seen.add(url)
        metadata = {"source_name": "OpenAI News"}
        model = _model(title, entry)
        product = _product(title, entry)
        if model:
            metadata["model"] = model
        if product:
            metadata["product"] = product
        signals.append(Signal(id=_id("openai_news", url), source_type=SignalSourceType.NEWS, source_adapter="openai_news", title=title, content=(_text(entry.get("summary") or entry.get("description") or entry.get("content")) or title)[:1000], url=url, author=_text(entry.get("author")) or None, published_at=_dt(entry.get("published_at") or entry.get("date")), tags=[value for value in ["openai", model, product] if value], metadata=metadata))
        if limit is not None and len(signals) >= limit:
            break
    return signals


def _model(title: str, entry: dict[str, Any]) -> str:
    explicit = _text(entry.get("model"))
    if explicit:
        return explicit
    match = re.search(r"\b(GPT-\d+(?:\.\d+)?|o\d+(?:-[\w-]+)?|DALL-E\s*\d+)\b", title, re.I)
    return match.group(1) if match else ""


def _product(title: str, entry: dict[str, Any]) -> str:
    explicit = _text(entry.get("product"))
    if explicit:
        return explicit
    lowered = title.lower()
    for product in ("chatgpt", "api", "sora", "codex"):
        if product in lowered:
            return product
    return ""
