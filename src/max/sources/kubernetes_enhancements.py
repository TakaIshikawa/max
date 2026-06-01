"""Kubernetes enhancements source adapter."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://raw.githubusercontent.com/kubernetes/enhancements/master/keps/sig-release/release-notes/release-1.31.yaml"


def _text(value: object) -> str:
    return str(value or "").strip()


def _items(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("enhancements", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _url(item: dict) -> str:
    return _text(item.get("url") or item.get("issue_url") or item.get("kep_url") or item.get("html_url"))


def _stable_id(url: str, title: str) -> str:
    return "kubernetes_enhancements:" + hashlib.sha256(f"{url}|{title}".encode()).hexdigest()[:16]


class KubernetesEnhancementsAdapter(SourceAdapter):
    """Fetch Kubernetes enhancement metadata and normalize it as NEWS signals."""

    @property
    def name(self) -> str:
        return "kubernetes_enhancements"

    @property
    def source_type(self) -> str:
        return SignalSourceType.NEWS.value

    @property
    def feed_url(self) -> str:
        return _text(self._config.get("feed_url") or self._config.get("url") or DEFAULT_URL)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []
        async with httpx.AsyncClient(timeout=float(self._config.get("timeout", 30))) as client:
            try:
                response = await fetch_with_retry(self.feed_url, client, adapter_name=self.name)
                payload = response.json()
            except Exception:
                logger.warning("Kubernetes enhancements fetch failed: %s", self.feed_url, exc_info=True)
                return []

        signals: list[Signal] = []
        for item in _items(payload):
            title = _text(item.get("title") or item.get("name"))
            url = _url(item)
            if not title or not url:
                continue
            sig = _text(item.get("sig"))
            stage = _text(item.get("stage"))
            milestone = _text(item.get("milestone") or item.get("release"))
            signals.append(
                Signal(
                    id=_stable_id(url, title),
                    source_type=SignalSourceType.NEWS,
                    source_adapter=self.name,
                    title=title,
                    content=_text(item.get("summary") or item.get("description") or title),
                    url=url,
                    published_at=None,
                    tags=[tag for tag in ["kubernetes", sig, stage, milestone] if tag],
                    metadata={
                        "sig": sig or None,
                        "stage": stage or None,
                        "milestone": milestone or None,
                        "canonical_url": url,
                        "issue_url": _text(item.get("issue_url")) or url,
                    },
                )
            )
            if len(signals) >= limit:
                break
        return signals
