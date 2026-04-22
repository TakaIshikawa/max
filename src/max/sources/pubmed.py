"""PubMed source adapter — clinical evidence signals via NCBI E-utilities."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone

import httpx

from max.sources.base import SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

_DEFAULT_QUERIES = [
    "digital health AND clinical workflow",
    "EHR usability OR clinician burnout",
    "AI diagnosis AND patient safety",
]

# High-impact journals → higher credibility
_HIGH_IMPACT_JOURNALS = {
    "the new england journal of medicine", "nejm",
    "the lancet", "lancet",
    "jama", "the journal of the american medical association",
    "bmj", "british medical journal",
    "nature medicine",
    "nature digital medicine", "npj digital medicine",
    "annals of internal medicine",
    "circulation",
    "journal of clinical oncology",
}

_MID_IMPACT_JOURNALS = {
    "journal of medical internet research", "jmir",
    "journal of the american medical informatics association", "jamia",
    "bmc medical informatics and decision making",
    "international journal of medical informatics",
    "journal of biomedical informatics",
    "telemedicine and e-health",
    "digital health",
    "health informatics journal",
    "applied clinical informatics",
    "journal of healthcare engineering",
}


def _get_api_key() -> str | None:
    """Resolve NCBI API key from env or vault."""
    key = os.environ.get("NCBI_API_KEY")
    if key:
        return key
    try:
        result = subprocess.run(
            ["vault", "get", "ncbi/api_key"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _journal_credibility(journal_name: str) -> float:
    """Map journal name to credibility score."""
    lower = journal_name.lower().strip()
    if any(j in lower for j in _HIGH_IMPACT_JOURNALS):
        return 0.9
    if any(j in lower for j in _MID_IMPACT_JOURNALS):
        return 0.6
    return 0.4


def _extract_tags(title: str, mesh_terms: list[str]) -> list[str]:
    """Build tags from MeSH terms and title keywords."""
    tags: set[str] = set()
    for term in mesh_terms[:8]:
        # Simplify MeSH terms (e.g. "Artificial Intelligence" → "artificial-intelligence")
        simplified = term.lower().replace(" ", "-")
        tags.add(simplified)
    kw_map = {
        "ehr": "ehr", "electronic health": "ehr",
        "fhir": "fhir", "telemedicine": "telemedicine",
        "artificial intelligence": "ai", " ai ": "ai",
        "machine learning": "ml", "deep learning": "ml",
        "clinical decision": "cds", "patient safety": "patient-safety",
        "burnout": "burnout", "interoperability": "interoperability",
    }
    title_lower = title.lower()
    for keyword, tag in kw_map.items():
        if keyword in title_lower:
            tags.add(tag)
    tags.add("pubmed")
    return sorted(tags)[:10]


def _parse_date(date_str: str) -> datetime | None:
    """Parse PubMed date string (e.g. '2026 Apr 15' or '2026/04/15')."""
    for fmt in ("%Y %b %d", "%Y/%m/%d", "%Y %b", "%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class PubMedAdapter(SourceAdapter):
    @property
    def name(self) -> str:
        return "pubmed"

    @property
    def source_type(self) -> str:
        return SignalSourceType.SURVEY.value

    @property
    def queries(self) -> list[str]:
        return self._config.get("queries", _DEFAULT_QUERIES)

    @property
    def max_results_per_query(self) -> int:
        return self._config.get("max_results_per_query", 10)

    @property
    def recent_days(self) -> int:
        return self._config.get("recent_days", 30)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen_pmids: set[str] = set()
        api_key = _get_api_key()

        # Date filter: last N days
        min_date = (datetime.now(timezone.utc) - timedelta(days=self.recent_days)).strftime("%Y/%m/%d")

        async with httpx.AsyncClient(timeout=30) as client:
            for i, query in enumerate(self.queries):
                if len(signals) >= limit:
                    break
                if i > 0:
                    await asyncio.sleep(0.5)  # rate-limit courtesy

                # Step 1: ESearch — get PMIDs
                search_params: dict = {
                    "db": "pubmed",
                    "term": query,
                    "retmax": self.max_results_per_query,
                    "sort": "date",
                    "retmode": "json",
                    "mindate": min_date,
                    "datetype": "pdat",
                }
                if api_key:
                    search_params["api_key"] = api_key

                try:
                    resp = await fetch_with_retry(
                        ESEARCH_URL, client,
                        adapter_name=self.name,
                        params=search_params,
                    )
                    search_data = resp.json()
                    pmids = search_data.get("esearchresult", {}).get("idlist", [])
                except Exception:
                    logger.warning("PubMed search failed for query: %s", query, exc_info=True)
                    continue

                # Filter already-seen PMIDs
                new_pmids = [p for p in pmids if p not in seen_pmids]
                if not new_pmids:
                    continue
                for p in new_pmids:
                    seen_pmids.add(p)

                # Step 2: ESummary — get article metadata
                summary_params: dict = {
                    "db": "pubmed",
                    "id": ",".join(new_pmids),
                    "retmode": "json",
                }
                if api_key:
                    summary_params["api_key"] = api_key

                await asyncio.sleep(0.4)  # rate-limit between steps

                try:
                    resp = await fetch_with_retry(
                        ESUMMARY_URL, client,
                        adapter_name=self.name,
                        params=summary_params,
                    )
                    summary_data = resp.json()
                    result = summary_data.get("result", {})
                except Exception:
                    logger.warning("PubMed summary failed for PMIDs: %s", new_pmids, exc_info=True)
                    continue

                for pmid in new_pmids:
                    if len(signals) >= limit:
                        break
                    article = result.get(pmid)
                    if not article or not isinstance(article, dict):
                        continue

                    title = article.get("title", "")
                    journal = article.get("fulljournalname") or article.get("source", "")
                    pub_date_str = article.get("pubdate", "")

                    # Extract author list
                    authors = []
                    for author in article.get("authors", []):
                        if isinstance(author, dict):
                            authors.append(author.get("name", ""))

                    # Extract MeSH terms (available in some ESummary responses)
                    mesh_terms: list[str] = []

                    signals.append(Signal(
                        source_type=SignalSourceType.SURVEY,
                        source_adapter=self.name,
                        title=title,
                        content=title,  # ESummary doesn't include abstracts
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        author=authors[0] if authors else None,
                        published_at=_parse_date(pub_date_str),
                        tags=_extract_tags(title, mesh_terms),
                        credibility=_journal_credibility(journal),
                        metadata={
                            "pmid": pmid,
                            "journal": journal,
                            "authors": authors[:5],
                            "pub_date": pub_date_str,
                            "doi": article.get("elocationid", ""),
                            "search_query": query,
                        },
                    ))

        return signals[:limit]
