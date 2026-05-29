"""npm package quality score source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class NpmPackageQualityScoreAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "npm_package_quality_score"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def packages(self) -> list[str]:
        return _strings(self._config.get("packages"))

    @property
    def queries(self) -> list[str]:
        return _strings(self._config.get("queries"))

    @property
    def api_url(self) -> str:
        return str(self._config.get("npms_api_url") or "https://api.npms.io/v2").strip().rstrip("/")

    @property
    def timeout(self) -> float:
        return _float(self._config.get("timeout"), 30.0)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        payloads: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for package in self.packages:
                if len(payloads) >= limit:
                    break
                response = await client.get(f"{self.api_url}/package/{package}")
                if response.status_code < 400:
                    payloads.append(response.json())
            for query in self.queries:
                if len(payloads) >= limit:
                    break
                response = await client.get(f"{self.api_url}/search", params={"q": query, "size": int(self._config.get("max_packages") or limit)})
                if response.status_code >= 400:
                    continue
                for result in response.json().get("results", []):
                    payloads.append(result)
                    if len(payloads) >= limit:
                        break
        return [_signal(p) for p in payloads[:limit]]


def _signal(payload: dict[str, Any]) -> Signal:
    package = payload.get("package") if isinstance(payload.get("package"), dict) else payload
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    detail = score.get("detail") if isinstance(score.get("detail"), dict) else {}
    name = str(package.get("name") or payload.get("name") or "unknown-package")
    final = _float(score.get("final"), 0.0)
    return Signal(
        id=_id("npm-quality", name, package.get("version") or ""),
        source_type=SignalSourceType.REGISTRY,
        source_adapter="npm_package_quality_score",
        title=f"{name} npm quality score",
        content=f"{name} has npm quality score {final:.2f}.",
        url=str(package.get("links", {}).get("npm") or f"https://www.npmjs.com/package/{name}"),
        published_at=datetime.now(timezone.utc),
        tags=["npm", "quality-score", name.lower()],
        credibility=min(max(final, 0.0), 1.0) or 0.5,
        metadata={
            "package": name,
            "version": package.get("version") or "",
            "license": package.get("license") or "",
            "repository": package.get("links", {}).get("repository") or package.get("repository") or "",
            "links": package.get("links") or {},
            "quality": _float(detail.get("quality"), 0.0),
            "popularity": _float(detail.get("popularity"), 0.0),
            "maintenance": _float(detail.get("maintenance"), 0.0),
            "final_score": final,
            "signal_role": "market",
        },
    )


def _strings(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    return [str(v).strip() for v in values if str(v).strip()]


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _id(*parts: object) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16]
