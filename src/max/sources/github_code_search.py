"""GitHub code search source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class GitHubCodeSearchAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "github_code_search"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def api_url(self) -> str:
        return str(self._config.get("github_api_url") or "https://api.github.com").strip().rstrip("/")

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        headers = {"Accept": "application/vnd.github+json"}
        token = self._config.get("github_token") or self._config.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        signals: list[Signal] = []
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            for query in _queries(self._config):
                response = await client.get(f"{self.api_url}/search/code", params={"q": query, "per_page": int(self._config.get("max_results_per_query") or limit)})
                if response.status_code >= 400:
                    continue
                for item in response.json().get("items", []):
                    signals.append(_signal(item, query))
                    if len(signals) >= limit:
                        return signals
        return signals


def _queries(config: dict[str, Any]) -> list[str]:
    base = _strings(config.get("queries")) or [""]
    repos = _strings(config.get("repositories"))
    languages = _strings(config.get("languages"))
    queries = []
    for q in base:
        parts = [q]
        parts.extend(f"repo:{r}" for r in repos)
        parts.extend(f"language:{l}" for l in languages)
        text = " ".join(p for p in parts if p).strip()
        if text:
            queries.append(text)
    return queries


def _signal(item: dict[str, Any], query: str) -> Signal:
    repo = item.get("repository") if isinstance(item.get("repository"), dict) else {}
    full_name = repo.get("full_name") or item.get("repository_full_name") or ""
    html_url = item.get("html_url") or ""
    return Signal(
        id=_id("github-code", full_name, item.get("path"), query),
        source_type=SignalSourceType.REGISTRY,
        source_adapter="github_code_search",
        title=f"{full_name} code match: {item.get('path') or item.get('name')}",
        content=f"Code search matched {query}.",
        url=str(html_url),
        published_at=datetime.now(timezone.utc),
        tags=["github", "code-search"],
        credibility=min(max(float(item.get("score") or 0) / 100, 0.2), 1.0),
        metadata={"path": item.get("path") or "", "repository": full_name, "language": item.get("language") or "", "score": item.get("score") or 0, "html_url": html_url, "matched_query": query, "source_url": html_url, "signal_role": "solution"},
    )


def _strings(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    return [str(v).strip() for v in values if str(v).strip()]


def _id(*parts: object) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16]
