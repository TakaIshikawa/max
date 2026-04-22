"""ArXiv source adapter — research direction signals via arXiv API."""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"

_DEFAULT_CATEGORIES = ["cs.AI", "cs.CL", "cs.SE"]
_DEFAULT_QUERIES = ["ti:agent AND ti:tool", "ti:LLM OR ti:language model"]


def _normalize_whitespace(text: str) -> str:
    """Collapse whitespace/newlines in arXiv titles and abstracts."""
    return re.sub(r"\s+", " ", text).strip()


def _extract_arxiv_id(entry_id: str) -> str:
    """Extract arXiv ID from entry URL (e.g. 'http://arxiv.org/abs/2404.12345v1')."""
    parts = entry_id.rstrip("/").split("/")
    return parts[-1] if parts else entry_id


def _extract_tags(title: str, categories: list[str]) -> list[str]:
    """Build tags from paper categories and title keywords."""
    tags: set[str] = set()
    for cat in categories[:5]:
        tags.add(cat.lower())
    kw_map = {
        "agent": "agent", "llm": "llm", "language model": "llm",
        "rag": "rag", "retrieval": "rag", "embedding": "embedding",
        "transformer": "transformer", "attention": "attention",
        "tool": "tool-use", "code": "code", "benchmark": "benchmark",
    }
    title_lower = title.lower()
    for keyword, tag in kw_map.items():
        if keyword in title_lower:
            tags.add(tag)
    tags.add("arxiv")
    return sorted(tags)[:10]


def _parse_entries(xml_text: str) -> list[dict]:
    """Parse arXiv Atom XML response into a list of entry dicts."""
    entries: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        preview = xml_text[:200] if xml_text else "(empty)"
        logger.warning("Failed to parse arXiv XML response: %s", preview)
        return entries

    for entry in root.findall(f"{_ATOM_NS}entry"):
        title_el = entry.find(f"{_ATOM_NS}title")
        summary_el = entry.find(f"{_ATOM_NS}summary")
        id_el = entry.find(f"{_ATOM_NS}id")
        published_el = entry.find(f"{_ATOM_NS}published")

        if title_el is None or id_el is None:
            continue

        # Authors
        authors = []
        for author_el in entry.findall(f"{_ATOM_NS}author"):
            name_el = author_el.find(f"{_ATOM_NS}name")
            if name_el is not None and name_el.text:
                authors.append(name_el.text)

        # Categories
        categories = []
        primary_el = entry.find(f"{_ARXIV_NS}primary_category")
        if primary_el is not None:
            categories.append(primary_el.get("term", ""))
        for cat_el in entry.findall(f"{_ATOM_NS}category"):
            term = cat_el.get("term", "")
            if term and term not in categories:
                categories.append(term)

        entries.append({
            "title": _normalize_whitespace(title_el.text or ""),
            "summary": _normalize_whitespace(summary_el.text or "") if summary_el is not None else "",
            "id": (id_el.text or "").strip(),
            "published": (published_el.text or "").strip() if published_el is not None else "",
            "authors": authors,
            "categories": categories,
        })

    return entries


def _parse_datetime(date_str: str) -> datetime | None:
    """Parse ISO 8601 datetime from arXiv."""
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class ArxivAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "arxiv"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SURVEY.value

    @property
    def categories(self) -> list[str]:
        return self._config.get("categories", _DEFAULT_CATEGORIES)

    @property
    def queries(self) -> list[str]:
        return self._config.get("queries", _DEFAULT_QUERIES)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_ids: set[str] = set()
        per_query = max(limit // len(self.queries), 5) if self.queries else limit

        headers = {
            "User-Agent": "max-signal-fetcher/1.0 (research; https://github.com)",
        }

        async with httpx.AsyncClient(
            timeout=30, headers=headers, follow_redirects=True,
        ) as client:
            for i, query in enumerate(self.queries):
                if len(signals) >= limit:
                    break
                if i > 0:
                    await asyncio.sleep(3)  # arXiv rate-limit courtesy

                # Build category filter: cat:cs.AI OR cat:cs.CL
                cat_filter = " OR ".join(f"cat:{c}" for c in self.categories)
                full_query = f"({cat_filter}) AND ({query})"

                try:
                    resp = await fetch_with_retry(
                        ARXIV_API,
                        client,
                        adapter_name=self.name,
                        max_retries=3,
                        backoff_base=3.0,
                        params={
                            "search_query": full_query,
                            "sortBy": "submittedDate",
                            "sortOrder": "descending",
                            "max_results": per_query,
                        },
                    )
                    entries = _parse_entries(resp.text)
                except Exception:
                    logger.warning("ArXiv fetch failed for query: %s", query, exc_info=True)
                    continue

                for entry in entries:
                    arxiv_id = _extract_arxiv_id(entry["id"])
                    if arxiv_id in seen_ids:
                        continue
                    seen_ids.add(arxiv_id)

                    signals.append(Signal(
                        source_type=SignalSourceType.SURVEY,
                        source_adapter=self.name,
                        title=entry["title"],
                        content=entry["summary"][:1000],
                        url=entry["id"],
                        author=entry["authors"][0] if entry["authors"] else None,
                        published_at=_parse_datetime(entry["published"]),
                        tags=_extract_tags(entry["title"], entry["categories"]),
                        credibility=0.6,
                        metadata={
                            "arxiv_id": arxiv_id,
                            "categories": entry["categories"][:5],
                            "authors": entry["authors"][:5],
                            "primary_category": entry["categories"][0] if entry["categories"] else "",
                            "search_query": query,
                        },
                    ))

                    if len(signals) >= limit:
                        break

        return signals[:limit]
