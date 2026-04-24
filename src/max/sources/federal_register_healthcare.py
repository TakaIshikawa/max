"""Federal Register healthcare regulatory change source adapter."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://www.federalregister.gov/api/v1"
DOCUMENTS_ENDPOINT = "/documents.json"

_DEFAULT_AGENCIES = [
    "centers-for-medicare-medicaid-services",
    "food-and-drug-administration",
    "health-and-human-services-department",
    "health-and-human-services-department-office-for-civil-rights",
]
_DEFAULT_TOPICS = ["health-care", "medicare", "medicaid", "public-health"]
_DEFAULT_SEARCH_TERMS = [
    "healthcare",
    "health care",
    "medical",
    "patient",
    "compliance",
]
_DEFAULT_DOCUMENT_TYPES = ["RULE", "PRORULE", "NOTICE"]
_DEFAULT_MAX_AGE_DAYS = 90

_ROADMAP_TYPES = {"rule", "proposed rule"}
_REPORT_TYPES = {"notice", "presidential document"}


class FederalRegisterHealthcareAdapter(SourceAdapter):
    """Fetch healthcare regulatory change signals from the Federal Register API."""

    config_keys = [
        "agencies",
        "topics",
        "search_terms",
        "document_types",
        "max_age_days",
        "base_url",
    ]
    required_keys: list[str] = []
    description = (
        "Fetches Federal Register healthcare rules, proposed rules, notices, and "
        "guidance-like regulatory change signals."
    )

    @property
    def name(self) -> str:
        return "federal_register_healthcare"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def base_url(self) -> str:
        configured = self._config.get("base_url")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().rstrip("/")
        return DEFAULT_BASE_URL

    @property
    def agencies(self) -> list[str]:
        return self._configured_terms("agencies", _DEFAULT_AGENCIES)

    @property
    def topics(self) -> list[str]:
        return self._configured_terms("topics", _DEFAULT_TOPICS)

    @property
    def search_terms(self) -> list[str]:
        return self._configured_terms("search_terms", _DEFAULT_SEARCH_TERMS)

    @property
    def document_types(self) -> list[str]:
        values = self._configured_terms("document_types", _DEFAULT_DOCUMENT_TYPES)
        return [_api_document_type(value) for value in values if _api_document_type(value)]

    @property
    def max_age_days(self) -> int | None:
        value = self._config.get("max_age_days", _DEFAULT_MAX_AGE_DAYS)
        if value is None:
            return None
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return _DEFAULT_MAX_AGE_DAYS
        return max(parsed, 0)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        terms = self.search_terms or [None]

        async with httpx.AsyncClient(timeout=30) as client:
            for term in terms:
                if len(signals) >= limit:
                    break

                data = await self._fetch_documents(client, term=term, limit=limit)
                for document in _documents(data):
                    if len(signals) >= limit:
                        break

                    signal = _document_to_signal(document, adapter_name=self.name, search_term=term)
                    if signal is None or not self._passes_filters(signal):
                        continue

                    if signal.id in seen:
                        continue
                    seen.add(signal.id)
                    signals.append(signal)

        return signals[:limit]

    async def _fetch_documents(
        self,
        client: httpx.AsyncClient,
        *,
        term: str | None,
        limit: int,
    ) -> dict[str, Any] | None:
        try:
            response = await fetch_with_retry(
                f"{self.base_url}{DOCUMENTS_ENDPOINT}",
                client,
                adapter_name=self.name,
                params=self._query_params(term=term, limit=limit),
                headers={"User-Agent": "max-federal-register-healthcare-adapter/0.1"},
            )
            data = response.json()
            return data if isinstance(data, dict) else None
        except AdapterFetchError as e:
            logger.warning("%s: failed to fetch Federal Register documents: %s", self.name, e)
        except ValueError as e:
            logger.warning("%s: failed to parse Federal Register response: %s", self.name, e)
        except httpx.RequestError as e:
            logger.warning("%s: Federal Register request failed: %s", self.name, e)
        return None

    def _query_params(self, *, term: str | None, limit: int) -> list[tuple[str, str | int]]:
        params: list[tuple[str, str | int]] = [
            ("per_page", max(min(limit, 100), 1)),
            ("order", "newest"),
        ]
        if term:
            params.append(("conditions[term]", term))

        cutoff = _cutoff_date(self.max_age_days)
        if cutoff:
            params.append(("conditions[publication_date][gte]", cutoff))

        for agency in self.agencies:
            params.append(("conditions[agencies][]", agency))
        for topic in self.topics:
            params.append(("conditions[topics][]", topic))
        for document_type in self.document_types:
            params.append(("conditions[type][]", document_type))

        return params

    def _passes_filters(self, signal: Signal) -> bool:
        if self.document_types:
            configured = {_normalized_document_type(value) for value in self.document_types}
            if _normalized_document_type(signal.metadata.get("document_type")) not in configured:
                return False

        published_at = signal.published_at
        max_age_days = self.max_age_days
        if max_age_days is not None and published_at is not None:
            compare_at = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
            if compare_at < datetime.now(timezone.utc) - timedelta(days=max_age_days):
                return False

        if self.search_terms:
            searchable = _searchable_text(signal)
            term = signal.metadata.get("search_term")
            if term and str(term).lower() in searchable:
                return True
            return any(search_term.lower() in searchable for search_term in self.search_terms)

        return True


def _document_to_signal(
    document: dict[str, Any],
    *,
    adapter_name: str,
    search_term: str | None,
) -> Signal | None:
    if not isinstance(document, dict):
        return None

    document_number = _string_or_none(document.get("document_number"))
    title = _string_or_none(document.get("title")) or _string_or_none(document.get("name"))
    if not title:
        return None

    url = _string_or_none(
        document.get("html_url")
        or document.get("url")
        or document.get("pdf_url")
        or document.get("public_inspection_pdf_url")
    )
    if not url:
        return None

    abstract = _string_or_none(document.get("abstract"))
    action = _string_or_none(document.get("action"))
    summary = _string_or_none(document.get("summary"))
    content = _join_present([abstract, action, summary, title])[:2000]

    document_type = _string_or_none(document.get("type")) or "Unknown"
    agency_names = _agency_names(document.get("agencies"))
    publication_date = _string_or_none(document.get("publication_date"))
    published_at = _parse_datetime(publication_date)
    effective_on = _string_or_none(document.get("effective_on"))
    docket_id = _first_string(document.get("docket_ids") or document.get("docket_id"))
    citation = _string_or_none(
        document.get("citation")
        or document.get("volume")
        and document.get("start_page")
        and f"{document.get('volume')} FR {document.get('start_page')}"
    )
    comment_url = _string_or_none(
        document.get("comment_url")
        or document.get("comments_url")
        or document.get("regulations_dot_gov_url")
    )

    metadata = {
        "agency_names": agency_names,
        "document_type": document_type,
        "publication_date": publication_date,
        "effective_on": effective_on,
        "comment_url": comment_url,
        "docket_id": docket_id,
        "citation": citation,
        "document_number": document_number,
        "search_term": search_term,
        "signal_role": "problem",
    }

    return Signal(
        id=_signal_id(adapter_name, document_number, url, title, publication_date),
        source_type=_source_type(document_type, title, content),
        source_adapter=adapter_name,
        title=title[:240],
        content=content,
        url=url,
        author=", ".join(agency_names) if agency_names else None,
        published_at=published_at,
        tags=_build_tags(document_type, agency_names, title, content),
        credibility=_credibility(document_type, bool(citation), bool(effective_on)),
        metadata=metadata,
    )


def _documents(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    results = data.get("results")
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


def _source_type(document_type: str, title: str, content: str) -> SignalSourceType:
    normalized = _normalized_document_type(document_type)
    if normalized in _ROADMAP_TYPES:
        return SignalSourceType.ROADMAP
    if _is_guidance_like(title, content):
        return SignalSourceType.REPORT
    if normalized in _REPORT_TYPES:
        return SignalSourceType.REPORT
    return SignalSourceType.REPORT


def _build_tags(
    document_type: str,
    agency_names: list[str],
    title: str,
    content: str,
) -> list[str]:
    tags = ["federal-register", "healthcare", _normalized_document_type(document_type)]
    tags.extend(_slug(name) for name in agency_names[:4])
    if _is_guidance_like(title, content):
        tags.append("guidance")
    return _dedupe([tag for tag in tags if tag])[:10]


def _credibility(document_type: str, has_citation: bool, has_effective_date: bool) -> float:
    normalized = _normalized_document_type(document_type)
    score = 0.7 if normalized in _ROADMAP_TYPES else 0.6
    if has_citation:
        score += 0.1
    if has_effective_date:
        score += 0.05
    return min(score, 0.9)


def _agency_names(value: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(value, list):
        return names
    for agency in value:
        if not isinstance(agency, dict):
            continue
        name = _string_or_none(agency.get("name") or agency.get("raw_name") or agency.get("short_name"))
        if name:
            names.append(name)
    return _dedupe(names)


def _api_document_type(value: object) -> str:
    normalized = _normalized_document_type(value)
    mapping = {
        "rule": "RULE",
        "final rule": "RULE",
        "proposed rule": "PRORULE",
        "prorule": "PRORULE",
        "notice": "NOTICE",
        "presidential document": "PRESDOCU",
        "presdocu": "PRESDOCU",
    }
    return mapping.get(normalized, str(value or "").strip().upper())


def _normalized_document_type(value: object) -> str:
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    aliases = {
        "rule": "rule",
        "final rule": "rule",
        "rules": "rule",
        "prorule": "proposed rule",
        "proposed rules": "proposed rule",
        "notice": "notice",
        "notices": "notice",
        "presdocu": "presidential document",
    }
    return aliases.get(text, text)


def _searchable_text(signal: Signal) -> str:
    parts = [
        signal.title,
        signal.content,
        signal.metadata.get("document_type"),
        signal.metadata.get("docket_id"),
        signal.metadata.get("citation"),
        " ".join(signal.metadata.get("agency_names") or []),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _is_guidance_like(title: str, content: str) -> bool:
    searchable = f"{title} {content}".lower()
    return any(term in searchable for term in ("guidance", "policy statement", "interpretation"))


def _signal_id(
    adapter_name: str,
    document_number: str | None,
    url: str,
    title: str,
    publication_date: str | None,
) -> str:
    key = document_number or "\x1f".join([url, title, publication_date or ""])
    digest = hashlib.sha1(key.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"{adapter_name}:{digest}"


def _cutoff_date(max_age_days: int | None) -> str | None:
    if max_age_days is None or max_age_days <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=max_age_days)).date().isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text = f"{text}T00:00:00+00:00"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _join_present(values: list[str | None]) -> str:
    return "\n".join(value for value in values if value)


def _first_string(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            text = _string_or_none(item)
            if text:
                return text
        return None
    return _string_or_none(value)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
