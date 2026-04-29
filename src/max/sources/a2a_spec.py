"""Agent-to-Agent specification source adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from max.sources.base import AdapterFetchError, SourceAdapter, fetch_with_retry
from max.sources.errors import SourceParseError
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITEMS = 100
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_KEY_VALUE_RE = re.compile(r"^\s*(?:[-*]\s*)?\**([A-Za-z][A-Za-z _-]{1,32})\**\s*:\s*(.+?)\s*$")
_DATE_RE = re.compile(r"\b(?:20\d{2}-\d{2}-\d{2}|20\d{2}-Q[1-4]|20\d{2})\b")
_JSON_CONTAINER_KEYS = (
    "spec_updates",
    "specUpdates",
    "items",
    "sections",
    "capabilities",
    "requirements",
    "changes",
    "signals",
    "data",
    "results",
)
_TITLE_KEYS = ("title", "name", "heading", "headline", "label", "capability", "requirement")
_CONTENT_KEYS = ("content", "summary", "description", "body", "text", "details", "rationale")
_SECTION_KEYS = ("section", "category", "area", "theme", "topic", "domain")
_URL_KEYS = ("url", "source_url", "spec_url", "canonical_url", "link")
_AUTHOR_KEYS = ("author", "publisher", "source")
_DATE_KEYS = ("updated_at", "updated", "published_at", "published", "date", "version_date")
_EVIDENCE_KEYS = ("evidence", "evidence_snippet", "evidenceSnippet", "snippet", "source_excerpt")
_TAG_KEYS = ("tags", "topics", "keywords", "terms")
_EXAMPLE_RE = re.compile(r"\b(example|sample|walkthrough|tutorial)\b", re.IGNORECASE)

_CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "capability": (
        "capability",
        "skill",
        "task",
        "artifact",
        "message",
        "discovery",
        "agent card",
        "agentcard",
    ),
    "lifecycle": (
        "lifecycle",
        "state",
        "status",
        "created",
        "submitted",
        "working",
        "completed",
        "failed",
        "canceled",
    ),
    "transport": (
        "transport",
        "http",
        "json-rpc",
        "json rpc",
        "stream",
        "sse",
        "webhook",
        "push notification",
    ),
    "security": (
        "security",
        "authentication",
        "authorization",
        "oauth",
        "token",
        "credential",
        "permission",
        "scope",
    ),
    "interoperability-gap": (
        "interoperability",
        "compatibility",
        "gap",
        "ambiguous",
        "undefined",
        "fragmentation",
        "conformance",
    ),
}


class A2ASpecAdapter(SourceAdapter):
    """Read Agent-to-Agent specification snapshots as protocol opportunity signals."""

    config_keys = [
        "spec_urls",
        "local_paths",
        "sections",
        "keywords",
        "max_items",
        "include_examples",
    ]
    required_keys: list[str] = []
    description = (
        "Reads Agent-to-Agent specification Markdown, text, and JSON snapshots "
        "as protocol capability, lifecycle, transport, security, and interoperability signals."
    )

    @property
    def name(self) -> str:
        return "a2a_spec"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def spec_urls(self) -> list[str]:
        return _string_list(self._config.get("spec_urls"))

    @property
    def local_paths(self) -> list[str]:
        return _string_list(self._config.get("local_paths"))

    @property
    def sections(self) -> list[str]:
        return _string_list(self._config.get("sections"))

    @property
    def keywords(self) -> list[str]:
        return _string_list(self._config.get("keywords"))

    @property
    def include_examples(self) -> bool:
        value = self._config.get("include_examples", True)
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off"}
        return bool(value)

    @property
    def max_items(self) -> int:
        value = self._config.get("max_items", _DEFAULT_MAX_ITEMS)
        if isinstance(value, bool):
            return _DEFAULT_MAX_ITEMS
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return _DEFAULT_MAX_ITEMS

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = min(limit, self.max_items)
        signals: list[Signal] = []
        seen: set[str] = set()

        for local_path in self.local_paths:
            if len(signals) >= item_limit:
                break
            try:
                self._append_signals(
                    signals,
                    self._read_local_path(local_path),
                    source_label=local_path,
                    source_url=_file_url(local_path),
                    limit=item_limit,
                    seen=seen,
                )
            except SourceParseError as exc:
                logger.warning("%s: skipping malformed spec file %s: %s", self.name, local_path, exc)

        if len(signals) < item_limit and self.spec_urls:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for spec_url in self.spec_urls:
                    if len(signals) >= item_limit:
                        break
                    text = await self._fetch_spec_url(spec_url, client)
                    if text is None:
                        continue
                    try:
                        self._append_signals(
                            signals,
                            text,
                            source_label=spec_url,
                            source_url=spec_url,
                            limit=item_limit,
                            seen=seen,
                        )
                    except SourceParseError as exc:
                        logger.warning("%s: skipping malformed spec URL %s: %s", self.name, spec_url, exc)

        return signals[:item_limit]

    def _read_local_path(self, local_path: str) -> str:
        try:
            return Path(local_path).read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise SourceParseError(
                f"Unable to read Agent-to-Agent specification snapshot: {local_path}",
                adapter_name=self.name,
            ) from exc

    async def _fetch_spec_url(self, spec_url: str, client: httpx.AsyncClient) -> str | None:
        try:
            response = await fetch_with_retry(spec_url, client, adapter_name=self.name)
        except AdapterFetchError as exc:
            logger.warning("%s: failed to fetch spec URL %s: %s", self.name, spec_url, exc)
            return None
        except Exception as exc:
            logger.warning("%s: failed to fetch spec URL %s: %s", self.name, spec_url, exc)
            return None
        return response.text

    def _append_signals(
        self,
        signals: list[Signal],
        text: str,
        *,
        source_label: str,
        source_url: str,
        limit: int,
        seen: set[str],
    ) -> None:
        for item in _parse_spec_items(text, source_label=source_label):
            if len(signals) >= limit:
                break
            signal = _signal_from_item(
                item,
                adapter_name=self.name,
                source_url=source_url,
                section_filters=self.sections,
                keyword_filters=self.keywords,
                include_examples=self.include_examples,
            )
            if signal is None or signal.id in seen:
                continue
            seen.add(signal.id)
            signals.append(signal)


def _parse_spec_items(text: str, *, source_label: str) -> list[dict[str, Any]]:
    stripped = text.lstrip()
    if _looks_like_json(source_label, stripped):
        return _extract_json_items(_parse_json(stripped, source_label))
    return _parse_text_sections(text, source_label=source_label)


def _looks_like_json(source_label: str, stripped_text: str) -> bool:
    suffix = Path(urlparse(source_label).path or source_label).suffix.lower()
    return suffix in {".json", ".jsonl"} or stripped_text.startswith(("{", "["))


def _parse_json(text: str, source_label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceParseError(
            f"Malformed Agent-to-Agent specification JSON: {source_label}",
            adapter_name="a2a_spec",
        ) from exc


def _extract_json_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    for key in _JSON_CONTAINER_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return _items_from_mapping(value)

    return [data]


def _items_from_mapping(value: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for section, payload in value.items():
        if isinstance(payload, str):
            items.append({"section": section, "title": section, "content": payload})
        elif isinstance(payload, dict):
            items.append({"section": section, **payload})
        elif isinstance(payload, list):
            for child in payload:
                if isinstance(child, dict):
                    items.append({"section": section, **child})
                elif isinstance(child, str):
                    items.append({"section": section, "title": section, "content": child})
    return items


def _parse_text_sections(text: str, *, source_label: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current_title: str | None = None
    current_level: int | None = None
    current_lines: list[str] = []
    saw_heading = False

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            saw_heading = True
            _append_text_item(items, current_title, current_level, current_lines, source_label)
            current_title = _clean_text(match.group(2))
            current_level = len(match.group(1))
            current_lines = []
            continue
        current_lines.append(line)

    _append_text_item(items, current_title, current_level, current_lines, source_label)
    if saw_heading:
        return items

    for index, paragraph in enumerate(re.split(r"\n\s*\n", text.strip()), start=1):
        content = _clean_markdown_content(paragraph)
        if content:
            items.append(
                {
                    "title": _title_from_content(content, index),
                    "section": "Agent-to-Agent specification",
                    "content": content,
                    "heading_level": None,
                    "year": _extract_year(source_label),
                }
            )
    return items


def _append_text_item(
    items: list[dict[str, Any]],
    title: str | None,
    level: int | None,
    lines: list[str],
    source_label: str,
) -> None:
    if not title:
        return
    content = _clean_markdown_content("\n".join(lines))
    if not content:
        return

    fields = _extract_markdown_fields(lines)
    items.append(
        {
            "title": title,
            "section": fields.get("section") or fields.get("area") or title,
            "content": fields.get("summary") or fields.get("description") or content,
            "evidence": fields.get("evidence") or fields.get("snippet"),
            "updated_at": fields.get("updated") or fields.get("date"),
            "heading_level": level,
            "year": _extract_year(source_label),
        }
    )


def _extract_markdown_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        match = _KEY_VALUE_RE.match(line)
        if not match:
            continue
        key = _clean_text(match.group(1)).lower().replace("_", " ")
        value = _clean_text(match.group(2))
        if key and value:
            fields[key] = value
    return fields


def _signal_from_item(
    item: dict[str, Any],
    *,
    adapter_name: str,
    source_url: str,
    section_filters: list[str],
    keyword_filters: list[str],
    include_examples: bool,
) -> Signal | None:
    title = _first_text(item, _TITLE_KEYS) or _first_text(item, _SECTION_KEYS)
    content = _content_text(item)
    section = _first_text(item, _SECTION_KEYS) or title or "Agent-to-Agent specification"
    evidence = _first_text(item, _EVIDENCE_KEYS)
    if not title or not content:
        return None

    searchable = " ".join(part for part in [title, section, content, evidence] if part)
    if not include_examples and _EXAMPLE_RE.search(searchable):
        return None
    if not _matches_any(section, section_filters):
        return None

    matched_keywords = _matched_terms(searchable, keyword_filters)
    if keyword_filters and not matched_keywords:
        return None

    categories = _classify_categories(searchable)
    if not categories and not matched_keywords:
        return None
    protocol_terms = _matched_category_terms(searchable)

    updated_at = _first_text(item, _DATE_KEYS) or _extract_date(searchable)
    published_at = _parse_datetime(updated_at)
    year = _parse_int(item.get("year")) or (
        published_at.year if published_at else _extract_year(searchable)
    )
    if published_at is None and year is not None:
        published_at = datetime(year, 1, 1, tzinfo=timezone.utc)

    metadata = {
        "section": section,
        "categories": categories,
        "protocol_terms": protocol_terms,
        "updated_at": updated_at,
        "evidence_snippet": evidence,
        "heading_level": _parse_int(item.get("heading_level")),
        "year": year,
        "matched_keywords": matched_keywords,
        "source_spec_url": source_url,
        "include_examples": include_examples,
        "signal_role": "solution" if "interoperability-gap" not in categories else "problem",
    }

    return Signal(
        id=_stable_id(adapter_name, source_url, section, title, content),
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=title[:240],
        content=_compose_content(content, evidence)[:1200],
        url=_first_text(item, _URL_KEYS) or source_url,
        author=_first_text(item, _AUTHOR_KEYS) or "Agent-to-Agent specification",
        published_at=published_at,
        tags=_build_tags(item, section, categories, protocol_terms, matched_keywords),
        credibility=0.82,
        metadata=metadata,
    )


def _content_text(item: dict[str, Any]) -> str | None:
    return _first_text(item, _CONTENT_KEYS) or _first_text(item, _EVIDENCE_KEYS)


def _compose_content(content: str, evidence: str | None) -> str:
    if not evidence or evidence.lower() in content.lower():
        return content
    return f"{content} Evidence: {evidence}"


def _classify_categories(value: str) -> list[str]:
    value_lower = value.lower()
    categories: list[str] = []
    for category, terms in _CATEGORY_TERMS.items():
        if any(term in value_lower for term in terms):
            categories.append(category)
    return categories


def _matched_category_terms(value: str) -> list[str]:
    value_lower = value.lower()
    terms: list[str] = []
    seen: set[str] = set()
    for category_terms in _CATEGORY_TERMS.values():
        for term in category_terms:
            if term in value_lower:
                slug = _slug(term)
                if slug and slug not in seen:
                    seen.add(slug)
                    terms.append(term)
    return terms


def _build_tags(
    item: dict[str, Any],
    section: str,
    categories: list[str],
    protocol_terms: list[str],
    matched_keywords: list[str],
) -> list[str]:
    tags = ["a2a", "protocol", "interoperability"]
    tags.extend(categories)
    tags.extend(protocol_terms)
    tags.extend(_slug_tokens(section))
    for key in _TAG_KEYS:
        tags.extend(_string_list(item.get(key)))
    tags.extend(matched_keywords)

    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        slug = _slug(tag)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        normalized.append(slug)
    return normalized


def _matches_any(value: str, filters: list[str]) -> bool:
    if not filters:
        return True
    value_lower = value.lower()
    return any(term.lower() in value_lower for term in filters)


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


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for key in keys:
        normalized_key = _normalize_key(key)
        if normalized_key in normalized:
            return normalized[normalized_key]
    return None


def _first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value = _first_present(row, keys)
    if value is None:
        return None
    if isinstance(value, list):
        text = ", ".join(str(item) for item in value if str(item).strip())
    elif isinstance(value, dict):
        return None
    else:
        text = str(value)
    text = _clean_text(text)
    return text or None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Iterable):
        values = [str(item) for item in value if str(item).strip()]
    else:
        values = []

    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = item.strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _title_from_content(content: str, index: int) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", content, maxsplit=1)[0]
    words = sentence.split()
    title = " ".join(words[:10]).strip(" .:")
    return title or f"Agent-to-Agent specification note {index}"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_markdown_content(value: str) -> str:
    lines = [line.strip() for line in value.strip().splitlines()]
    return _clean_text("\n".join(line for line in lines if line))


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _slug_tokens(value: str) -> list[str]:
    slug = _slug(value)
    return [part for part in slug.split("-") if len(part) > 2][:4]


def _parse_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit() and len(text) == 4:
        return datetime(int(text), 1, 1, tzinfo=timezone.utc)
    match = re.fullmatch(r"20\d{2}-Q[1-4]", text, flags=re.IGNORECASE)
    if match:
        year, quarter = text.upper().split("-Q", 1)
        month = ((int(quarter) - 1) * 3) + 1
        return datetime(int(year), month, 1, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _extract_date(value: str) -> str | None:
    match = _DATE_RE.search(value)
    return match.group(0) if match else None


def _extract_year(value: str) -> int | None:
    match = re.search(r"(20\d{2})", value)
    return int(match.group(1)) if match else None


def _file_url(local_path: str) -> str:
    return f"file://{Path(local_path).resolve()}"


def _stable_id(adapter_name: str, source_url: str, section: str, title: str, content: str) -> str:
    raw = "\x1f".join([source_url, section, title, content])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{adapter_name}:{digest}"
