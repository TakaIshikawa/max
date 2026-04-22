"""PyPI registry source adapter — AI/ML packages via RSS + JSON API."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

from max.sources.base import SourceAdapter
from max.sources.errors import (
    SourceAuthError,
    SourceParseError,
    SourceRateLimitError,
    SourceTransientError,
)
from max.sources.retry import with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

RSS_UPDATES = "https://pypi.org/rss/updates.xml"
RSS_PACKAGES = "https://pypi.org/rss/packages.xml"
PYPI_JSON = "https://pypi.org/pypi/{name}/json"
PYPISTATS_API = "https://pypistats.org/api/packages/{name}/recent"

_DEFAULT_KEYWORDS = {
    "ai", "llm", "agent", "mcp", "langchain", "openai", "anthropic",
    "transformer", "embedding", "rag", "vector", "gpt", "claude",
    "huggingface", "diffusion", "neural", "deep-learning", "machine-learning",
    "chatbot", "prompt", "tokenizer", "inference",
}


class PyPIRegistryAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "pypi_registry"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REGISTRY.value

    @property
    def keywords(self) -> set[str]:
        return set(self._configured_terms("keywords", _DEFAULT_KEYWORDS))

    @property
    def include_release_trends(self) -> bool:
        return bool(self._config.get("include_release_trends", False))

    @property
    def lookback_days(self) -> int:
        return max(int(self._config.get("lookback_days", 30)), 1)

    @property
    def min_releases(self) -> int:
        return max(int(self._config.get("min_releases", 3)), 1)

    @with_retry(max_retries=3, base_delay=1.0, adapter_name="pypi_registry")
    async def _fetch_rss(self, client: httpx.AsyncClient, rss_url: str) -> list[tuple[str, str, datetime | None]]:
        """Fetch and parse PyPI RSS feed with retry logic."""
        try:
            resp = await client.get(rss_url)
            resp.raise_for_status()
            return _parse_rss(resp.text)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                retry_after = e.response.headers.get("Retry-After")
                retry_seconds = float(retry_after) if retry_after else None
                raise SourceRateLimitError(
                    f"Rate limit exceeded for {rss_url}",
                    adapter_name=self.name,
                    retry_after=retry_seconds,
                ) from e
            elif status in (401, 403):
                raise SourceAuthError(
                    f"Authentication failed (HTTP {status}) for {rss_url}",
                    adapter_name=self.name,
                ) from e
            elif 500 <= status < 600:
                raise SourceTransientError(
                    f"Server error (HTTP {status}) for {rss_url}",
                    adapter_name=self.name,
                ) from e
            else:
                raise SourceTransientError(
                    f"HTTP {status} for {rss_url}",
                    adapter_name=self.name,
                ) from e
        except ET.ParseError as e:
            raise SourceParseError(
                f"Failed to parse RSS feed: {rss_url}",
                adapter_name=self.name,
            ) from e

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_names: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for rss_url in (RSS_UPDATES, RSS_PACKAGES):
                if len(signals) >= limit:
                    break
                try:
                    candidates = await self._fetch_rss(client, rss_url)
                except (SourceRateLimitError, SourceAuthError):
                    # Rate limit or auth errors affect all feeds — raise immediately
                    raise
                except (
                    SourceTransientError,
                    SourceParseError,
                    httpx.RequestError,
                    httpx.TimeoutException,
                ):
                    # Transient, parse, or network errors for this feed — log and try next feed
                    logger.warning("Failed to fetch PyPI RSS: %s", rss_url, exc_info=True)
                    continue

                for pkg_name, pkg_link, pub_date in candidates:
                    if len(signals) >= limit:
                        break
                    normalized = pkg_name.lower().split("/")[0].strip()
                    if normalized in seen_names:
                        continue
                    if not _matches_keywords(normalized, self.keywords):
                        continue
                    seen_names.add(normalized)

                    # Enrich via JSON API
                    info = await _fetch_package_info(client, normalized)
                    if not info:
                        continue

                    downloads_week = await _fetch_download_stats(client, normalized)
                    credibility = (
                        min(downloads_week / 100_000, 1.0)
                        if downloads_week is not None
                        else 0.3
                    )

                    tags = _build_tags(info, normalized)
                    release_trend = _analyze_release_trend(
                        info,
                        lookback_days=self.lookback_days,
                        min_releases=self.min_releases,
                    )

                    signals.append(
                        Signal(
                            source_type=SignalSourceType.REGISTRY,
                            source_adapter=self.name,
                            title=f"{info['name']}@{info['version']}",
                            content=(info.get("summary") or info["name"])[:500],
                            url=info.get("package_url") or pkg_link,
                            author=info.get("author"),
                            published_at=pub_date,
                            tags=tags,
                            credibility=credibility,
                            metadata={
                                "pypi_name": info["name"],
                                "version": info["version"],
                                "classifiers": info.get("classifiers", [])[:10],
                                "requires_python": info.get("requires_python"),
                                "downloads_week": downloads_week,
                                "project_urls": info.get("project_urls") or {},
                                "release_trend": release_trend,
                            },
                        )
                    )

                    if (
                        self.include_release_trends
                        and release_trend["is_trending"]
                        and len(signals) < limit
                    ):
                        trend_tags = sorted({*tags, "release-trend"})[:10]
                        signals.append(
                            Signal(
                                source_type=SignalSourceType.TRENDING,
                                source_adapter=self.name,
                                title=f"{info['name']} release velocity spike",
                                content=_format_release_trend_content(info, release_trend),
                                url=info.get("package_url") or pkg_link,
                                author=info.get("author"),
                                published_at=_parse_iso_datetime(release_trend["latest_release_at"])
                                or pub_date,
                                tags=trend_tags,
                                credibility=max(credibility, 0.6),
                                metadata={
                                    "signal_kind": "release_trend",
                                    "pypi_name": info["name"],
                                    "version": info["version"],
                                    "downloads_week": downloads_week,
                                    "project_urls": info.get("project_urls") or {},
                                    "release_trend": release_trend,
                                },
                            )
                        )

        return signals[:limit]


def _parse_rss(xml_text: str) -> list[tuple[str, str, datetime | None]]:
    """Parse PyPI RSS XML → list of (package_name, link, pub_date)."""
    results: list[tuple[str, str, datetime | None]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return results

    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")

        title = title_el.text if title_el is not None and title_el.text else ""
        link = link_el.text if link_el is not None and link_el.text else ""

        # Title is usually "package_name version" — extract the name
        pkg_name = title.split(" ")[0].strip() if title else ""
        if not pkg_name:
            continue

        pub_date = _parse_rfc822(pub_el.text) if pub_el is not None and pub_el.text else None
        results.append((pkg_name, link, pub_date))

    return results


def _matches_keywords(pkg_name: str, keywords: set[str]) -> bool:
    """Check if package name contains any of the configured keywords."""
    lower = pkg_name.lower().replace("-", " ").replace("_", " ")
    parts = set(lower.split())
    return bool(parts & keywords) or any(kw in lower for kw in keywords)


async def _fetch_package_info(client: httpx.AsyncClient, name: str) -> dict | None:
    """Fetch package metadata from PyPI JSON API."""
    try:
        resp = await client.get(PYPI_JSON.format(name=name))
        resp.raise_for_status()
        data = resp.json()
        info = data.get("info", {})
        return {
            "name": info.get("name", name),
            "version": info.get("version", "0.0.0"),
            "summary": info.get("summary", ""),
            "author": info.get("author") or info.get("author_email"),
            "classifiers": info.get("classifiers", []),
            "requires_python": info.get("requires_python"),
            "package_url": info.get("package_url"),
            "project_urls": info.get("project_urls"),
            "keywords": info.get("keywords") or "",
            "releases": data.get("releases", {}),
        }
    except httpx.HTTPError:
        # Any HTTP error (status or network) — log but return None (package may not exist or be unavailable)
        logger.debug("Failed to fetch PyPI package info for %s", name, exc_info=True)
        return None
    except (ValueError, KeyError, TypeError):
        # Parse error — log but return None
        logger.debug("Failed to parse PyPI package info for %s", name, exc_info=True)
        return None


async def _fetch_download_stats(client: httpx.AsyncClient, name: str) -> int | None:
    """Fetch weekly download count from pypistats.org. Returns None on failure."""
    try:
        resp = await client.get(PYPISTATS_API.format(name=name))
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("last_week")
    except httpx.HTTPError:
        # Any HTTP error (status or network) — log but return None (stats may not be available)
        logger.debug("Failed to fetch download stats for %s", name, exc_info=True)
        return None
    except (ValueError, KeyError, TypeError):
        # Parse error — log but return None
        logger.debug("Failed to parse download stats for %s", name, exc_info=True)
        return None


def _build_tags(info: dict, pkg_name: str) -> list[str]:
    """Build tags from classifiers, keywords, and package name."""
    tags: set[str] = set()

    # Map classifiers
    classifier_map = {
        "Artificial Intelligence": "ai",
        "Machine Learning": "ml",
        "Natural Language": "nlp",
        "Neural": "neural",
        "Deep Learning": "ml",
    }
    for classifier in info.get("classifiers", []):
        for key, tag in classifier_map.items():
            if key in classifier:
                tags.add(tag)

    # Scan keywords field
    keywords_str = info.get("keywords", "")
    if keywords_str:
        for kw in keywords_str.replace(",", " ").split():
            if kw.lower().strip() in _DEFAULT_KEYWORDS:
                tags.add(kw.lower().strip())

    # Scan package name
    name_lower = pkg_name.lower().replace("-", " ").replace("_", " ")
    for kw in _DEFAULT_KEYWORDS:
        if kw in name_lower:
            tags.add(kw)

    tags.add("python")
    return sorted(tags)[:10]


def _analyze_release_trend(
    info: dict,
    *,
    lookback_days: int,
    min_releases: int,
    now: datetime | None = None,
) -> dict:
    """Summarize recent PyPI release velocity from JSON API release history."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    cutoff = current_time - timedelta(days=max(lookback_days, 1))

    releases = info.get("releases") or {}
    release_events = _release_events(releases)
    recent_events = [
        event for event in release_events if cutoff <= event["uploaded_at"] <= current_time
    ]
    recent_events.sort(key=lambda event: event["uploaded_at"], reverse=True)

    recent_count = len(recent_events)
    version_spike = _has_version_spike(release_events, cutoff)
    is_trending = recent_count >= min_releases or version_spike
    latest_release_at = recent_events[0]["uploaded_at"] if recent_events else None

    reasons: list[str] = []
    if recent_count >= min_releases:
        reasons.append("release_velocity")
    if version_spike:
        reasons.append("version_spike")

    return {
        "is_trending": is_trending,
        "reasons": reasons,
        "lookback_days": max(lookback_days, 1),
        "min_releases": max(min_releases, 1),
        "recent_release_count": recent_count,
        "recent_versions": [event["version"] for event in recent_events[:10]],
        "latest_release_at": latest_release_at.isoformat() if latest_release_at else None,
        "version_spike": version_spike,
    }


def _release_events(releases: dict) -> list[dict]:
    """Return one upload timestamp per version, sorted from oldest to newest."""
    events: list[dict] = []
    for version, files in releases.items():
        uploaded_times: list[datetime] = []
        if isinstance(files, list):
            for file_info in files:
                if not isinstance(file_info, dict):
                    continue
                uploaded_at = _parse_iso_datetime(
                    file_info.get("upload_time_iso_8601") or file_info.get("upload_time")
                )
                if uploaded_at is not None:
                    uploaded_times.append(uploaded_at)
        if uploaded_times:
            events.append({"version": str(version), "uploaded_at": max(uploaded_times)})

    events.sort(key=lambda event: event["uploaded_at"])
    return events


def _has_version_spike(release_events: list[dict], cutoff: datetime) -> bool:
    """Detect large version movement where the newer release landed inside the lookback."""
    previous_version: tuple[int, int, int] | None = None
    for event in release_events:
        version = _version_tuple(event["version"])
        if version is None:
            continue
        if event["uploaded_at"] >= cutoff and previous_version is not None:
            major_delta = version[0] - previous_version[0]
            minor_delta = version[1] - previous_version[1] if major_delta == 0 else 0
            patch_delta = version[2] - previous_version[2] if major_delta == 0 and minor_delta == 0 else 0
            if major_delta >= 1 or minor_delta >= 2 or patch_delta >= 5:
                return True
        previous_version = version
    return False


def _version_tuple(version: str) -> tuple[int, int, int] | None:
    """Extract a simple major/minor/patch tuple from common Python versions."""
    match = re.match(r"^\D*(\d+)(?:\.(\d+))?(?:\.(\d+))?", version)
    if not match:
        return None
    major, minor, patch = match.groups(default="0")
    return int(major), int(minor), int(patch)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse PyPI JSON upload timestamps."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_release_trend_content(info: dict, release_trend: dict) -> str:
    """Build concise trend signal copy."""
    recent_count = release_trend["recent_release_count"]
    lookback_days = release_trend["lookback_days"]
    versions = ", ".join(release_trend["recent_versions"][:5])
    summary = info.get("summary") or info["name"]
    details = f"{recent_count} releases in the last {lookback_days} days"
    if release_trend["version_spike"]:
        details += " with a notable version jump"
    if versions:
        details += f" ({versions})"
    return f"{info['name']} shows release momentum: {details}. {summary}"[:500]


def _parse_rfc822(date_str: str) -> datetime | None:
    """Best-effort RFC 822 date parsing (PyPI RSS format)."""
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(date_str).replace(tzinfo=timezone.utc)
    except Exception:
        logger.debug("Failed to parse RFC822 date: %s", date_str, exc_info=True)
        return None
