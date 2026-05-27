"""PyPI project links source adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType


class PyPIProjectLinksAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "pypi_project_links"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def packages(self) -> list[str]:
        return _strings(self._config.get("packages") or self._config.get("package_names") or self._config.get("queries"))

    @property
    def api_url(self) -> str:
        return str(self._config.get("pypi_api_url") or "https://pypi.org/pypi").strip().rstrip("/")

    @property
    def timeout(self) -> float:
        return _float(self._config.get("timeout"), 30.0)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for package in self.packages[:limit]:
                response = await client.get(f"{self.api_url}/{package}/json")
                if response.status_code >= 400:
                    continue
                payload = response.json()
                info = payload.get("info") if isinstance(payload, dict) else {}
                if isinstance(info, dict):
                    signals.append(_signal(package, info))
        return signals[:limit]


def _signal(package: str, info: dict[str, Any]) -> Signal:
    urls = info.get("project_urls") if isinstance(info.get("project_urls"), dict) else {}
    link_categories = {str(k).lower().replace(" ", "_"): str(v) for k, v in urls.items() if v}
    source_url = str(info.get("package_url") or f"https://pypi.org/project/{package}/")
    version = str(info.get("version") or "")
    classifiers = [str(c) for c in info.get("classifiers") or []]
    return Signal(
        id=_id("pypi-project-links", package, version),
        source_type=SignalSourceType.REGISTRY,
        source_adapter="pypi_project_links",
        title=f"{package} PyPI project links",
        content=str(info.get("summary") or f"{package} project metadata and links."),
        url=source_url,
        published_at=datetime.now(timezone.utc),
        tags=["pypi", "project-links", package.lower()],
        credibility=0.65,
        metadata={
            "package": package,
            "version": version,
            "project_urls": urls,
            "link_categories": link_categories,
            "documentation_url": _pick(urls, "Documentation", "Docs", "Homepage"),
            "source_url": _pick(urls, "Source", "Source Code", "Repository", "GitHub") or source_url,
            "issue_tracker_url": _pick(urls, "Issues", "Issue Tracker", "Bug Tracker"),
            "funding_url": _pick(urls, "Funding", "Sponsor"),
            "classifiers": classifiers,
            "license": info.get("license") or "",
            "requires_python": info.get("requires_python") or "",
            "release_freshness": info.get("upload_time") or info.get("version") or "",
            "signal_role": "market",
        },
    )


def _pick(urls: dict[str, Any], *names: str) -> str:
    lowered = {str(k).lower(): str(v) for k, v in urls.items() if v}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return ""


def _strings(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    out: list[str] = []
    for item in values:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _id(*parts: object) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16]
