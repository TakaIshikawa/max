"""Python PEP index source adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.sources.errors import SourceParseError
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_INDEX_URL = "https://peps.python.org/api/peps.json"
PEP_WEB_BASE = "https://peps.python.org"
_DEFAULT_STATUSES = ("active", "accepted", "final", "deferred")
_DEFAULT_KEYWORDS = (
    "build",
    "dependency",
    "dependencies",
    "distribution",
    "distutils",
    "import",
    "installer",
    "metadata",
    "packag",
    "pip",
    "pyproject",
    "tool",
    "typing",
    "virtual environment",
    "wheel",
)
_PEP_NUMBER_RE = re.compile(r"\b(?:pep[-\s]*)?(\d{1,5})\b", re.IGNORECASE)


class PythonPepsAdapter(SourceAdapter):
    """Fetches Python PEP index standards movement for tooling and packaging workflows."""

    config_keys = [
        "index_url",
        "local_path",
        "content",
        "statuses",
        "types",
        "topics",
        "keywords",
        "max_results",
    ]
    required_keys: list[str] = []
    description = (
        "Fetches Python PEP index standards metadata for developer tooling, "
        "packaging, typing, and compatibility workflow signals."
    )

    @property
    def name(self) -> str:
        return "python_peps"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def index_url(self) -> str:
        return str(self._config.get("index_url") or DEFAULT_INDEX_URL)

    @property
    def statuses(self) -> list[str]:
        return _normalized_list(self._config.get("statuses") or _DEFAULT_STATUSES)

    @property
    def types(self) -> list[str]:
        return _normalized_list(self._config.get("types"))

    @property
    def topics(self) -> list[str]:
        return _normalized_list(self._config.get("topics"))

    @property
    def keywords(self) -> list[str]:
        return _normalized_list(self._config.get("keywords") or _DEFAULT_KEYWORDS)

    @property
    def max_results(self) -> int:
        return _positive_int(self._config.get("max_results"), default=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        text = await self._load_index_text()
        if text is None:
            return []

        effective_limit = min(max(limit, 1), self.max_results)
        signals: list[Signal] = []
        seen: set[str] = set()

        try:
            items = _parse_pep_index(text)
        except SourceParseError as exc:
            logger.warning("%s: skipping malformed PEP index: %s", self.name, exc)
            return []

        for item in items:
            if len(signals) >= effective_limit:
                break
            signal = _signal_from_item(
                item,
                adapter_name=self.name,
                status_filters=self.statuses,
                type_filters=self.types,
                topic_filters=self.topics,
                keyword_filters=self.keywords,
            )
            if signal is None or signal.id in seen:
                continue
            seen.add(signal.id)
            signals.append(signal)

        return signals

    async def _load_index_text(self) -> str | None:
        content = self._config.get("content")
        if isinstance(content, str):
            return content

        local_path = self._config.get("local_path")
        if local_path:
            try:
                return Path(str(local_path)).read_text(encoding="utf-8-sig")
            except OSError as exc:
                logger.warning("%s: failed to read PEP index %s: %s", self.name, local_path, exc)
                return None

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                response = await fetch_with_retry(self.index_url, client, adapter_name=self.name)
            except AdapterFetchError as exc:
                logger.warning("%s: failed to fetch PEP index %s: %s", self.name, self.index_url, exc)
                return None
            except httpx.RequestError as exc:
                logger.warning("%s: failed to fetch PEP index %s: %s", self.name, self.index_url, exc)
                return None
        return response.text


def _parse_pep_index(text: str) -> list[dict[str, Any]]:
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped.startswith(("{", "[")):
        return _extract_json_items(_parse_json(stripped))
    return _parse_text_index(text)


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceParseError("Malformed Python PEP index JSON", adapter_name="python_peps") from exc


def _extract_json_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        container = _first_present(data, ("peps", "items", "results", "data"))
        if isinstance(container, dict):
            candidates = [
                {"number": number, **value} if isinstance(value, dict) else value
                for number, value in container.items()
            ]
        elif isinstance(container, list):
            candidates = container
        else:
            candidates = [
                {"number": number, **value}
                for number, value in data.items()
                if isinstance(value, dict) and _looks_like_pep_number(number)
            ]
    else:
        candidates = []

    items: list[dict[str, Any]] = []
    for candidate in candidates:
        if isinstance(candidate, dict):
            items.append(candidate)
    return items


def _parse_text_index(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in text.splitlines():
        normalized_line = re.sub(r"\s+", " ", line).strip()
        match = re.search(
            r"\bPEP\s+(?P<number>\d{1,5})\b\s*[-:]\s*(?P<title>.+?)"
            r"(?:\s+\((?P<status>Active|Accepted|Final|Deferred),\s*(?P<type>[^)]+)\))?$",
            normalized_line,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        items.append(
            {
                "number": match.group("number"),
                "title": match.group("title"),
                "status": match.group("status"),
                "type": match.group("type"),
            }
        )
    return items


def _signal_from_item(
    item: dict[str, Any],
    *,
    adapter_name: str,
    status_filters: list[str],
    type_filters: list[str],
    topic_filters: list[str],
    keyword_filters: list[str],
) -> Signal | None:
    pep_number = _normalize_pep_number(
        _first_text(item, ("number", "pep", "pep_number", "pepNumber", "id"))
    )
    title = _clean_title(_first_text(item, ("title", "name", "heading")))
    status = _title_case(_first_text(item, ("status", "state")))
    pep_type = _title_case(_first_text(item, ("type", "category", "pep_type", "pepType")))
    topic = _title_case(_first_text(item, ("topic", "area", "section")))
    url = _normalize_url(_first_text(item, ("url", "link", "html_url", "canonical_url")), pep_number)
    abstract = _first_text(item, ("abstract", "summary", "description", "content"))
    created = _first_text(item, ("created", "created_at", "date", "published_at"))

    if not pep_number or not title:
        return None
    if status_filters and _slug(status or "") not in status_filters:
        return None
    if type_filters and _slug(pep_type or "") not in type_filters:
        return None
    if topic_filters and _slug(topic or "") not in topic_filters:
        return None

    searchable = " ".join(part for part in [title, status, pep_type, topic, abstract] if part)
    matched_keywords = _matched_terms(searchable, keyword_filters)
    if keyword_filters and not matched_keywords:
        return None

    normalized_tags = _build_tags(
        status=status,
        pep_type=pep_type,
        topic=topic,
        matched_keywords=matched_keywords,
    )
    content = _compose_content(
        title=title,
        status=status,
        pep_type=pep_type,
        topic=topic,
        abstract=abstract,
    )
    metadata = {
        "pep_number": pep_number,
        "status": status,
        "type": pep_type,
        "topic": topic,
        "url": url,
        "matched_keywords": matched_keywords,
        "normalized_tags": normalized_tags,
        "signal_kind": "python_pep",
        "signal_role": "solution",
        "raw_metadata": item,
    }

    return Signal(
        id=_signal_id(adapter_name, pep_number),
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"PEP {pep_number}: {title}",
        content=content[:1200],
        url=url,
        author=_first_text(item, ("author", "authors", "sponsor", "delegate")),
        published_at=_parse_datetime(created),
        tags=normalized_tags,
        credibility=_credibility(status),
        metadata=metadata,
    )


def _compose_content(
    *,
    title: str,
    status: str | None,
    pep_type: str | None,
    topic: str | None,
    abstract: str | None,
) -> str:
    parts = [f"Python PEP standards signal for {title}."]
    descriptors = []
    if status:
        descriptors.append(f"Status: {status}")
    if pep_type:
        descriptors.append(f"Type: {pep_type}")
    if topic:
        descriptors.append(f"Topic: {topic}")
    if descriptors:
        parts.append("; ".join(descriptors) + ".")
    if abstract:
        parts.append(abstract)
    return " ".join(parts)


def _build_tags(
    *,
    status: str | None,
    pep_type: str | None,
    topic: str | None,
    matched_keywords: list[str],
) -> list[str]:
    tags = ["standards", "python", "pep"]
    if status:
        status_slug = _slug(status)
        tags.extend([status_slug, f"status-{status_slug}"])
    if pep_type:
        tags.append(f"type-{_slug(pep_type)}")
    if topic:
        tags.append(_slug(topic))
    tags.extend(_slug(term) for term in matched_keywords)

    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        slug = _slug(tag)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        normalized.append(slug)
    return normalized[:12]


def _matched_terms(value: str, terms: list[str]) -> list[str]:
    value_lower = value.lower()
    matches: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = term.strip().lower()
        if normalized and normalized in value_lower and normalized not in seen:
            seen.add(normalized)
            matches.append(term.strip())
    return matches


def _first_present(row: dict[str, Any], keys: Iterable[str]) -> Any:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for key in keys:
        normalized_key = _normalize_key(key)
        if normalized_key in normalized:
            return normalized[normalized_key]
    return None


def _first_text(row: dict[str, Any], keys: Iterable[str]) -> str | None:
    value = _first_present(row, keys)
    if value is None:
        return None
    if isinstance(value, list):
        text = ", ".join(str(item) for item in value if str(item).strip())
    elif isinstance(value, dict):
        return None
    else:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _clean_title(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"^PEP\s+\d{1,5}\s*[-:]\s*", "", value, flags=re.IGNORECASE).strip()


def _normalize_pep_number(value: str | None) -> str | None:
    if not value:
        return None
    match = _PEP_NUMBER_RE.search(value)
    if not match:
        return None
    return str(int(match.group(1)))


def _normalize_url(value: str | None, pep_number: str) -> str:
    if value:
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if value.startswith("/"):
            return f"{PEP_WEB_BASE}{value}"
    return f"{PEP_WEB_BASE}/pep-{int(pep_number):04d}/"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _credibility(status: str | None) -> float:
    normalized = _slug(status or "")
    if normalized in {"accepted", "final"}:
        return 0.82
    if normalized == "active":
        return 0.74
    if normalized == "deferred":
        return 0.62
    return 0.55


def _title_case(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(part.capitalize() for part in re.split(r"\s+", value.strip()))


def _normalized_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates: Iterable[object] = [value]
    elif isinstance(value, Iterable):
        candidates = value
    else:
        candidates = []

    result: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        slug = _slug(str(item))
        if slug and slug not in seen:
            seen.add(slug)
            result.append(slug)
    return result


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return max(int(str(value).strip()), 1)
    except (TypeError, ValueError):
        return default


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _looks_like_pep_number(value: object) -> bool:
    return bool(re.fullmatch(r"\d{1,5}", str(value).strip()))


def _signal_id(adapter_name: str, pep_number: str) -> str:
    digest = hashlib.sha1(pep_number.encode("utf-8")).hexdigest()[:12]
    return f"{adapter_name}:{digest}"
