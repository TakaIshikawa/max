"""AI coding trust and verification report adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
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
_YEAR_RE = re.compile(r"(20\d{2})")
_PERCENT_RE = re.compile(r"(?P<sign>[+-])?\s*(?P<value>\d+(?:\.\d+)?)\s*%")
_MULTIPLIER_RE = re.compile(r"(?<![\w.])(?P<value>\d+(?:\.\d+)?)\s*(?:x|×)\b", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_JSON_CONTAINER_KEYS = (
    "statistics",
    "stats",
    "metrics",
    "findings",
    "items",
    "reports",
    "signals",
    "sections",
    "data",
    "results",
)
_TITLE_KEYS = ("report_title", "title", "name", "heading", "headline")
_CONTENT_KEYS = ("statistic_text", "text", "content", "summary", "description", "body", "finding")
_LABEL_KEYS = ("statistic_label", "label", "metric", "metric_name", "name", "title")
_SECTION_KEYS = ("section", "category", "area", "theme", "topic")
_POPULATION_KEYS = ("population", "sample", "sample_description", "respondents", "audience")
_URL_KEYS = ("source_url", "report_url", "url", "canonical_url", "link")
_DATE_KEYS = ("published_at", "published", "date", "report_date", "snapshot_date", "created_at")
_VALUE_KEYS = ("value", "metric_value", "percent", "percentage", "multiplier", "delta")
_UNIT_KEYS = ("unit", "value_unit")


@dataclass(frozen=True)
class _ReportChunk:
    report_title: str
    section: str
    text: str
    source_label: str
    source_url: str
    url: str
    published_at: datetime | None = None
    population: str | None = None
    explicit_label: str | None = None
    explicit_value: float | None = None
    explicit_unit: str | None = None


@dataclass(frozen=True)
class _Statistic:
    label: str
    value: float
    unit: str
    text: str
    population: str | None
    role: str


class AICodeTrustReportsAdapter(SourceAdapter):
    """Read AI coding trust, review, verification, and productivity report stats."""

    @property
    def name(self) -> str:
        return "ai_code_trust_reports"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REPORT.value

    @property
    def report_urls(self) -> list[str]:
        return _string_list(self._config.get("report_urls"))

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
    def min_percent(self) -> float:
        return _parse_float(self._config.get("min_percent")) or 0.0

    @property
    def max_items(self) -> int:
        value = _parse_int(self._config.get("max_items"))
        return value if value and value > 0 else _DEFAULT_MAX_ITEMS

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        item_limit = min(limit, self.max_items)
        signals: list[Signal] = []
        seen: set[str] = set()

        for local_path in self.local_paths:
            if len(signals) >= item_limit:
                break
            text = self._read_local_path(local_path)
            self._append_signals(
                signals,
                text,
                source_label=local_path,
                source_url=_file_url(local_path),
                limit=item_limit,
                seen=seen,
            )

        if len(signals) < item_limit and self.report_urls:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for report_url in self.report_urls:
                    if len(signals) >= item_limit:
                        break
                    text = await self._fetch_report_url(report_url, client)
                    if text is None:
                        continue
                    self._append_signals(
                        signals,
                        text,
                        source_label=report_url,
                        source_url=report_url,
                        limit=item_limit,
                        seen=seen,
                    )

        return signals[:item_limit]

    def _read_local_path(self, local_path: str) -> str:
        try:
            return Path(local_path).read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise SourceParseError(
                f"Unable to read AI code trust report: {local_path}",
                adapter_name=self.name,
            ) from exc

    async def _fetch_report_url(self, report_url: str, client: httpx.AsyncClient) -> str | None:
        try:
            response = await fetch_with_retry(report_url, client, adapter_name=self.name)
        except AdapterFetchError as exc:
            logger.warning("%s: failed to fetch report URL %s: %s", self.name, report_url, exc)
            return None
        except Exception as exc:
            logger.warning("%s: failed to fetch report URL %s: %s", self.name, report_url, exc)
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
        for chunk in _parse_report_chunks(text, source_label=source_label, source_url=source_url):
            if len(signals) >= limit:
                break
            if not _matches_any(chunk.section, self.sections):
                continue
            matched_keywords = _matched_terms(
                " ".join([chunk.report_title, chunk.section, chunk.text]),
                self.keywords,
            )
            if self.keywords and not matched_keywords:
                continue
            for statistic in _extract_statistics(chunk):
                if len(signals) >= limit:
                    break
                if statistic.unit in {"percent", "delta_percent"} and abs(statistic.value) < self.min_percent:
                    continue
                signal = _signal_from_statistic(
                    statistic,
                    chunk,
                    adapter_name=self.name,
                    matched_keywords=matched_keywords,
                )
                if signal.id in seen:
                    continue
                seen.add(signal.id)
                signals.append(signal)


def _parse_report_chunks(text: str, *, source_label: str, source_url: str) -> list[_ReportChunk]:
    stripped = text.lstrip()
    if _looks_like_json(source_label, stripped):
        return _parse_json_chunks(_parse_json(stripped, source_label), source_label, source_url)
    return _parse_markdown_chunks(text, source_label=source_label, source_url=source_url)


def _parse_markdown_chunks(text: str, *, source_label: str, source_url: str) -> list[_ReportChunk]:
    report_title = _extract_markdown_title(text) or Path(urlparse(source_label).path).stem or "AI code trust report"
    chunks: list[_ReportChunk] = []
    current_section = report_title
    current_lines: list[str] = []

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            _append_markdown_lines(
                chunks,
                report_title=report_title,
                section=current_section,
                lines=current_lines,
                source_label=source_label,
                source_url=source_url,
            )
            current_section = _clean_text(match.group(2))
            current_lines = []
            continue
        current_lines.append(line)

    _append_markdown_lines(
        chunks,
        report_title=report_title,
        section=current_section,
        lines=current_lines,
        source_label=source_label,
        source_url=source_url,
    )
    return chunks


def _append_markdown_lines(
    chunks: list[_ReportChunk],
    *,
    report_title: str,
    section: str,
    lines: list[str],
    source_label: str,
    source_url: str,
) -> None:
    for line in lines:
        text = _markdown_line_to_text(line)
        if not text or not _contains_statistic(text):
            continue
        for sentence in _statistic_fragments(text):
            chunks.append(
                _ReportChunk(
                    report_title=report_title,
                    section=section,
                    text=sentence,
                    source_label=source_label,
                    source_url=source_url,
                    url=source_url,
                    published_at=_published_from_source(source_label),
                    population=_infer_population(sentence),
                )
            )


def _parse_json_chunks(data: Any, source_label: str, source_url: str) -> list[_ReportChunk]:
    if not isinstance(data, (dict, list)):
        return []
    report_title = "AI code trust report"
    published_at = _published_from_source(source_label)
    url = source_url
    if isinstance(data, dict):
        report_title = _first_text(data, _TITLE_KEYS) or report_title
        published_at = _parse_datetime(_first_present(data, _DATE_KEYS)) or published_at
        url = _first_text(data, _URL_KEYS) or url
    return list(
        _walk_json_chunks(
            data,
            report_title=report_title,
            section=report_title,
            source_label=source_label,
            source_url=source_url,
            url=url,
            published_at=published_at,
        )
    )


def _walk_json_chunks(
    value: Any,
    *,
    report_title: str,
    section: str,
    source_label: str,
    source_url: str,
    url: str,
    published_at: datetime | None,
) -> list[_ReportChunk]:
    chunks: list[_ReportChunk] = []
    if isinstance(value, list):
        for item in value:
            chunks.extend(
                _walk_json_chunks(
                    item,
                    report_title=report_title,
                    section=section,
                    source_label=source_label,
                    source_url=source_url,
                    url=url,
                    published_at=published_at,
                )
            )
        return chunks
    if not isinstance(value, dict):
        return chunks

    item_title = _first_text(value, _TITLE_KEYS)
    item_section = _first_text(value, _SECTION_KEYS) or section
    item_url = _first_text(value, _URL_KEYS) or url
    item_date = _parse_datetime(_first_present(value, _DATE_KEYS)) or published_at
    label = _first_text(value, _LABEL_KEYS)
    population = _first_text(value, _POPULATION_KEYS)
    explicit_value = _parse_float(_first_present(value, _VALUE_KEYS))
    explicit_unit = _normalize_unit(_first_text(value, _UNIT_KEYS))
    content = _first_text(value, _CONTENT_KEYS)

    text_parts = [part for part in [label, content] if part]
    if explicit_value is not None:
        rendered_value = _format_number(explicit_value)
        if explicit_unit == "percent":
            rendered_value = f"{rendered_value}%"
        elif explicit_unit == "multiplier":
            rendered_value = f"{rendered_value}x"
        text_parts.append(rendered_value)
    text = _clean_text(" ".join(text_parts))

    if text and (explicit_value is not None or _contains_statistic(text)):
        chunks.append(
            _ReportChunk(
                report_title=item_title or report_title,
                section=item_section,
                text=text,
                source_label=source_label,
                source_url=source_url,
                url=item_url,
                published_at=item_date,
                population=population or _infer_population(text),
                explicit_label=label,
                explicit_value=explicit_value,
                explicit_unit=explicit_unit,
            )
        )

    for key in _JSON_CONTAINER_KEYS:
        child = _first_present(value, (key,))
        if child is None:
            continue
        if isinstance(child, dict) and key == "sections":
            for child_section, payload in child.items():
                chunks.extend(
                    _walk_json_chunks(
                        payload,
                        report_title=report_title,
                        section=str(child_section),
                        source_label=source_label,
                        source_url=source_url,
                        url=item_url,
                        published_at=item_date,
                    )
                )
        else:
            chunks.extend(
                _walk_json_chunks(
                    child,
                    report_title=report_title,
                    section=item_section,
                    source_label=source_label,
                    source_url=source_url,
                    url=item_url,
                    published_at=item_date,
                )
            )
    return chunks


def _extract_statistics(chunk: _ReportChunk) -> list[_Statistic]:
    if chunk.explicit_value is not None and chunk.explicit_unit:
        label = chunk.explicit_label or _derive_label(chunk.text, chunk.explicit_unit)
        return [
            _Statistic(
                label=label,
                value=chunk.explicit_value,
                unit=chunk.explicit_unit,
                text=chunk.text,
                population=chunk.population,
                role=_signal_role(" ".join([label, chunk.text])),
            )
        ]

    statistics: list[_Statistic] = []
    for match in _PERCENT_RE.finditer(chunk.text):
        value = float(match.group("value"))
        sign = match.group("sign")
        if sign == "-":
            value = -value
        unit = "delta_percent" if sign or _looks_like_delta(chunk.text, match.start()) else "percent"
        label = _derive_label(chunk.text, unit)
        statistics.append(
            _Statistic(
                label=label,
                value=value,
                unit=unit,
                text=chunk.text,
                population=chunk.population,
                role=_signal_role(chunk.text),
            )
        )

    for match in _MULTIPLIER_RE.finditer(chunk.text):
        value = float(match.group("value"))
        label = _derive_label(chunk.text, "multiplier")
        statistics.append(
            _Statistic(
                label=label,
                value=value,
                unit="multiplier",
                text=chunk.text,
                population=chunk.population,
                role=_signal_role(chunk.text),
            )
        )

    return statistics


def _signal_from_statistic(
    statistic: _Statistic,
    chunk: _ReportChunk,
    *,
    adapter_name: str,
    matched_keywords: list[str],
) -> Signal:
    title = f"{statistic.label}: {_format_number(statistic.value)}{_unit_suffix(statistic.unit)}"
    metadata = {
        "statistic_label": statistic.label,
        "value": statistic.value,
        "unit": statistic.unit,
        "population": statistic.population,
        "section": chunk.section,
        "report_title": chunk.report_title,
        "signal_role": statistic.role,
        "statistic_text": statistic.text,
        "matched_keywords": matched_keywords,
        "source_report_url": chunk.source_url,
        "source_label": chunk.source_label,
    }
    published_at = chunk.published_at
    if published_at is None:
        year = _extract_year(chunk.source_label)
        if year is not None:
            published_at = datetime(year, 1, 1, tzinfo=timezone.utc)

    return Signal(
        id=_stable_id(
            adapter_name,
            chunk.source_url,
            chunk.section,
            statistic.label,
            statistic.text,
            statistic.unit,
            statistic.value,
        ),
        source_type=SignalSourceType.REPORT,
        source_adapter=adapter_name,
        title=title[:240],
        content=statistic.text[:1200],
        url=chunk.url,
        author="AI Code Trust Reports",
        published_at=published_at,
        tags=_tags_for_statistic(statistic, chunk, matched_keywords),
        credibility=_credibility(statistic),
        metadata=metadata,
    )


def _looks_like_json(source_label: str, stripped_text: str) -> bool:
    suffix = Path(urlparse(source_label).path or source_label).suffix.lower()
    return suffix in {".json", ".jsonl"} or stripped_text.startswith(("{", "["))


def _parse_json(text: str, source_label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceParseError(
            f"Malformed AI code trust JSON report: {source_label}",
            adapter_name="ai_code_trust_reports",
        ) from exc


def _extract_markdown_title(text: str) -> str | None:
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            return _clean_text(match.group(2))
    return None


def _markdown_line_to_text(line: str) -> str:
    text = line.strip()
    if not text:
        return ""
    if text.startswith("|") and text.endswith("|"):
        cells = [_clean_text(cell) for cell in text.strip("|").split("|")]
        if all(set(cell.replace(":", "").strip()) <= {"-"} for cell in cells):
            return ""
        return _clean_text(" ".join(cell for cell in cells if cell))
    text = re.sub(r"^\s*[-*+]\s+", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    return _clean_text(text)


def _statistic_fragments(text: str) -> list[str]:
    fragments = [fragment.strip() for fragment in _SENTENCE_SPLIT_RE.split(text) if fragment.strip()]
    return [fragment for fragment in fragments if _contains_statistic(fragment)] or [text]


def _contains_statistic(text: str) -> bool:
    return bool(_PERCENT_RE.search(text) or _MULTIPLIER_RE.search(text))


def _looks_like_delta(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - 40) : match_start + 80].lower()
    return any(
        term in window
        for term in (
            "increase",
            "increased",
            "decrease",
            "decreased",
            "more",
            "less",
            "faster",
            "slower",
            "delta",
            "change",
        )
    )


def _derive_label(text: str, unit: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" -:|.")
    cleaned = _PERCENT_RE.sub("", cleaned)
    cleaned = _MULTIPLIER_RE.sub("", cleaned)
    cleaned = re.sub(r"\b(value|rate|share|increase|decrease|delta)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:|.")
    if not cleaned:
        return {
            "percent": "Reported percentage",
            "delta_percent": "Reported percentage change",
            "multiplier": "Reported multiplier",
        }.get(unit, "Reported statistic")
    return cleaned[:120]


def _signal_role(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("trust", "distrust", "verify", "verification", "review")):
        return "trust"
    if any(term in lowered for term in ("security", "vulnerability", "finding", "risk")):
        return "risk"
    if any(term in lowered for term in ("productivity", "faster", "slower", "churn", "duplication")):
        return "productivity"
    return "problem"


def _infer_population(text: str) -> str | None:
    lowered = text.lower()
    if "developer" in lowered:
        return "developers"
    if "project" in lowered:
        return "projects"
    if "pull request" in lowered or "pr " in lowered:
        return "pull requests"
    if "organization" in lowered or "fortune" in lowered:
        return "organizations"
    if "agent run" in lowered:
        return "agent runs"
    return None


def _credibility(statistic: _Statistic) -> float:
    if statistic.unit == "multiplier" and statistic.value >= 4:
        return 0.84
    if statistic.unit in {"percent", "delta_percent"} and abs(statistic.value) >= 50:
        return 0.82
    return 0.76


def _tags_for_statistic(
    statistic: _Statistic,
    chunk: _ReportChunk,
    matched_keywords: list[str],
) -> list[str]:
    tags = ["ai-code", "trust", "report", statistic.unit, statistic.role]
    tags.extend(_slug_tokens(chunk.section))
    tags.extend(matched_keywords)
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        slug = _slug(tag)
        if slug and slug not in seen:
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
    if value is None or isinstance(value, (list, dict)):
        return None
    text = _clean_text(str(value))
    return text or None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    else:
        try:
            values = [str(item) for item in value if str(item).strip()]  # type: ignore[union-attr]
        except TypeError:
            values = []

    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = item.strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _normalize_unit(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _slug(value)
    if normalized in {"percent", "percentage", "pct", "share"}:
        return "percent"
    if normalized in {"delta", "delta-percent", "percentage-point", "percentage-points"}:
        return "delta_percent"
    if normalized in {"x", "multiplier", "multiple", "times"}:
        return "multiplier"
    return normalized or None


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    if text.endswith(("%", "x", "X", "×")):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: object) -> int | None:
    parsed = _parse_float(value)
    return int(parsed) if parsed is not None else None


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit() and len(text) == 4:
        return datetime(int(text), 1, 1, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _published_from_source(source_label: str) -> datetime | None:
    year = _extract_year(source_label)
    if year is None:
        return None
    return datetime(year, 1, 1, tzinfo=timezone.utc)


def _extract_year(value: str) -> int | None:
    match = _YEAR_RE.search(value)
    return int(match.group(1)) if match else None


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _slug_tokens(value: str) -> list[str]:
    slug = _slug(value)
    return [part for part in slug.split("-") if len(part) > 2][:4]


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _unit_suffix(unit: str) -> str:
    if unit in {"percent", "delta_percent"}:
        return "%"
    if unit == "multiplier":
        return "x"
    return ""


def _file_url(local_path: str) -> str:
    return f"file://{Path(local_path).resolve()}"


def _stable_id(
    adapter_name: str,
    source_url: str,
    section: str,
    label: str,
    text: str,
    unit: str,
    value: float,
) -> str:
    raw = "\x1f".join([source_url, section, label, text, unit, _format_number(value)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{adapter_name}:{digest}"
