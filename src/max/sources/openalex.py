"""OpenAlex source adapter for scholarly works."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

OPENALEX_WORKS_API = "https://api.openalex.org/works"

_DEFAULT_SEARCH_TERMS = [
    "artificial intelligence",
    "software engineering",
    "developer tools",
]


def _normalize_doi(value: str | None) -> str:
    """Return a bare DOI value from OpenAlex DOI URLs."""
    if not value:
        return ""
    doi = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            return doi[len(prefix):]
    return doi


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """Convert OpenAlex abstract_inverted_index into normal text."""
    if not inverted_index:
        return ""

    positions: dict[int, str] = {}
    for word, indexes in inverted_index.items():
        if not isinstance(word, str) or not isinstance(indexes, list):
            continue
        for index in indexes:
            if isinstance(index, int):
                positions[index] = word

    if not positions:
        return ""

    return " ".join(positions[index] for index in sorted(positions))


def _parse_publication_date(value: str | None) -> datetime | None:
    """Parse an OpenAlex publication_date value."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            logger.debug("Failed to parse OpenAlex publication date: %s", value, exc_info=True)
            return None


def _extract_authors(work: dict[str, Any]) -> list[str]:
    """Extract author display names from OpenAlex authorships."""
    authors: list[str] = []
    for authorship in work.get("authorships") or []:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author") or {}
        name = author.get("display_name") if isinstance(author, dict) else None
        if isinstance(name, str) and name.strip():
            authors.append(name.strip())
    return authors


def _extract_concepts(work: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract compact concept metadata from an OpenAlex work."""
    concepts: list[dict[str, Any]] = []
    for concept in work.get("concepts") or []:
        if not isinstance(concept, dict):
            continue
        display_name = concept.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            continue
        concepts.append(
            {
                "id": concept.get("id", ""),
                "display_name": display_name.strip(),
                "level": concept.get("level"),
                "score": concept.get("score"),
            }
        )
    return concepts


def _extract_venue(work: dict[str, Any]) -> dict[str, Any]:
    """Extract venue/source metadata from primary_location."""
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") if isinstance(primary_location, dict) else {}
    if not isinstance(source, dict):
        source = {}

    return {
        "id": source.get("id", ""),
        "display_name": source.get("display_name", ""),
        "type": source.get("type", ""),
        "issn_l": source.get("issn_l", ""),
        "issn": source.get("issn", []),
        "host_organization": source.get("host_organization", ""),
        "landing_page_url": primary_location.get("landing_page_url", "")
        if isinstance(primary_location, dict)
        else "",
        "pdf_url": primary_location.get("pdf_url", "") if isinstance(primary_location, dict) else "",
    }


def _canonical_url(work: dict[str, Any]) -> str:
    """Choose the most useful canonical URL for a work."""
    doi = work.get("doi")
    if isinstance(doi, str) and doi.strip():
        return doi.strip()

    primary_location = work.get("primary_location") or {}
    if isinstance(primary_location, dict):
        landing_page_url = primary_location.get("landing_page_url")
        if isinstance(landing_page_url, str) and landing_page_url.strip():
            return landing_page_url.strip()

    work_id = work.get("id")
    return work_id.strip() if isinstance(work_id, str) else ""


def _concept_filter_value(value: str) -> str:
    """Normalize configured concept IDs or URLs for OpenAlex filters."""
    concept = value.strip()
    if concept.startswith("https://openalex.org/"):
        return concept.rsplit("/", 1)[-1]
    return concept


def _build_filter(concepts: list[str], from_publication_date: str | None) -> str | None:
    """Build an OpenAlex filter string from configured profile params."""
    filters: list[str] = []
    if from_publication_date:
        filters.append(f"from_publication_date:{from_publication_date}")

    concept_ids = [_concept_filter_value(c) for c in concepts if isinstance(c, str) and c.strip()]
    if concept_ids:
        filters.append(f"concepts.id:{'|'.join(concept_ids)}")

    return ",".join(filters) if filters else None


def _tags_from_concepts(concepts: list[dict[str, Any]]) -> list[str]:
    tags = ["openalex"]
    for concept in concepts:
        display_name = concept.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            tags.append(display_name.strip().lower().replace(" ", "-"))
    return list(dict.fromkeys(tags))[:10]


def _work_to_signal(work: dict[str, Any], search_term: str | None = None) -> Signal | None:
    """Map an OpenAlex work dictionary into a Signal."""
    title = work.get("title") or work.get("display_name") or ""
    if not isinstance(title, str) or not title.strip():
        return None

    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
    authors = _extract_authors(work)
    concepts = _extract_concepts(work)
    venue = _extract_venue(work)
    doi = _normalize_doi(work.get("doi"))

    return Signal(
        source_type=SignalSourceType.ARTICLE,
        source_adapter="openalex",
        title=title.strip(),
        content=abstract[:2000] if abstract else title.strip(),
        url=_canonical_url(work),
        author=authors[0] if authors else None,
        published_at=_parse_publication_date(work.get("publication_date")),
        tags=_tags_from_concepts(concepts),
        credibility=0.65,
        metadata={
            "openalex_id": work.get("id", ""),
            "doi": doi,
            "cited_by_count": work.get("cited_by_count", 0),
            "concepts": concepts,
            "authors": authors,
            "venue": venue,
            "publication_date": work.get("publication_date", ""),
            "search_term": search_term or "",
        },
    )


class OpenAlexAdapter(SourceAdapter):
    """Fetches scholarly work signals from the OpenAlex Works API."""

    @property
    def name(self) -> str:
        return "openalex"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ARTICLE.value

    @property
    def search_terms(self) -> list[str]:
        return self._configured_terms("search_terms", _DEFAULT_SEARCH_TERMS)

    @property
    def concepts(self) -> list[str]:
        return [str(value) for value in self._config.get("concepts", []) if str(value).strip()]

    @property
    def from_publication_date(self) -> str | None:
        value = self._config.get("from_publication_date")
        return str(value).strip() if value else None

    @property
    def per_page(self) -> int:
        value = self._config.get("per_page", 25)
        try:
            per_page = int(value)
        except (TypeError, ValueError):
            per_page = 25
        return max(1, min(per_page, 200))

    @property
    def mailto(self) -> str | None:
        value = self._config.get("mailto")
        return str(value).strip() if value else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_ids: set[str] = set()
        filter_value = _build_filter(self.concepts, self.from_publication_date)
        search_terms = self.search_terms or [""]

        headers = {
            "User-Agent": "max-signal-fetcher/1.0 (mailto configured via profile)",
        }

        async with httpx.AsyncClient(
            timeout=30,
            headers=headers,
            follow_redirects=True,
        ) as client:
            for search_term in search_terms:
                if len(signals) >= limit:
                    break

                params: dict[str, Any] = {
                    "per-page": min(self.per_page, max(limit - len(signals), 1)),
                    "sort": "publication_date:desc",
                }
                if search_term:
                    params["search"] = search_term
                if filter_value:
                    params["filter"] = filter_value
                if self.mailto:
                    params["mailto"] = self.mailto

                response = await fetch_with_retry(
                    OPENALEX_WORKS_API,
                    client,
                    adapter_name=self.name,
                    max_retries=3,
                    backoff_base=1.0,
                    params=params,
                )
                data = response.json()
                results = data.get("results", []) if isinstance(data, dict) else []

                for work in results:
                    if not isinstance(work, dict):
                        continue
                    work_id = work.get("id") or work.get("doi") or work.get("title")
                    if isinstance(work_id, str) and work_id in seen_ids:
                        continue
                    if isinstance(work_id, str):
                        seen_ids.add(work_id)

                    signal = _work_to_signal(work, search_term or None)
                    if signal is None:
                        continue
                    signals.append(signal)

                    if len(signals) >= limit:
                        break

        return signals[:limit]
