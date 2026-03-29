"""PyPI registry source adapter — AI/ML packages via RSS + JSON API."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

RSS_UPDATES = "https://pypi.org/rss/updates.xml"
RSS_PACKAGES = "https://pypi.org/rss/packages.xml"
PYPI_JSON = "https://pypi.org/pypi/{name}/json"
PYPISTATS_API = "https://pypistats.org/api/packages/{name}/recent"

AI_KEYWORDS = {
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

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_names: set[str] = set()

        async with httpx.AsyncClient(timeout=30) as client:
            for rss_url in (RSS_UPDATES, RSS_PACKAGES):
                if len(signals) >= limit:
                    break
                try:
                    resp = await client.get(rss_url)
                    resp.raise_for_status()
                    candidates = _parse_rss(resp.text)
                except Exception:
                    logger.warning("Failed to fetch PyPI RSS: %s", rss_url, exc_info=True)
                    continue

                for pkg_name, pkg_link, pub_date in candidates:
                    if len(signals) >= limit:
                        break
                    normalized = pkg_name.lower().split("/")[0].strip()
                    if normalized in seen_names:
                        continue
                    if not _matches_ai_keywords(normalized):
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


def _matches_ai_keywords(pkg_name: str) -> bool:
    """Check if package name contains any AI-related keyword."""
    lower = pkg_name.lower().replace("-", " ").replace("_", " ")
    parts = set(lower.split())
    return bool(parts & AI_KEYWORDS) or any(kw in lower for kw in AI_KEYWORDS)


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
        }
    except Exception:
        return None


async def _fetch_download_stats(client: httpx.AsyncClient, name: str) -> int | None:
    """Fetch weekly download count from pypistats.org. Returns None on failure."""
    try:
        resp = await client.get(PYPISTATS_API.format(name=name))
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("last_week")
    except Exception:
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
            if kw.lower().strip() in AI_KEYWORDS:
                tags.add(kw.lower().strip())

    # Scan package name
    name_lower = pkg_name.lower().replace("-", " ").replace("_", " ")
    for kw in AI_KEYWORDS:
        if kw in name_lower:
            tags.add(kw)

    tags.add("python")
    return sorted(tags)[:10]


def _parse_rfc822(date_str: str) -> datetime | None:
    """Best-effort RFC 822 date parsing (PyPI RSS format)."""
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(date_str).replace(tzinfo=timezone.utc)
    except Exception:
        return None
