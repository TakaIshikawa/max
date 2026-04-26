"""METR-style AI productivity report adapter."""

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
_QUOTE_RE = re.compile(r"[\"“]([^\"”]{8,240})[\"”]")
_JSON_CONTAINER_KEYS = (
    "metrics",
    "statistics",
    "findings",
    "items",
    "reports",
    "signals",
    "sections",
    "data",
    "results",
)
_TITLE_KEYS = ("report_title", "title", "name", "heading", "headline")
_CONTENT_KEYS = (
    "finding",
    "finding_text",
    "quoted_finding",
    "quote",
    "text",
    "content",
    "summary",
    "description",
    "body",
)
_METRIC_KEYS = (
    "metric_name",
    "metric",
    "measure",
    "label",
    "statistic_label",
    "name",
    "title",
)
_SECTION_KEYS = ("section", "category", "area", "theme", "topic")
_TASK_CLASS_KEYS = ("task_class", "task_type", "task", "task_category", "class")
_SEGMENT_KEYS = (
    "participant_segment",
    "segment",
    "participants",
    "population",
    "sample",
    "cohort",
)
_CAVEAT_KEYS = ("caveat", "caveats", "limitation", "limitations", "notes", "warning")
_URL_KEYS = ("source_url", "report_url", "url", "canonical_url", "link")
_DATE_KEYS = ("published_at", "published", "date", "report_date", "snapshot_date", "created_at")
_VALUE_KEYS = (
    "value",
    "metric_value",
    "delta",
    "productivity_delta",
    "percent_change",
    "estimate",
)
_UNIT_KEYS = ("unit", "value_unit")
_TAG_KEYS = ("tags", "topics", "keywords")


@dataclass(frozen=True)
class _ReportChunk:
    report_title: str
    section: str
    text: str
    source_label: str
    source_url: str
    url: str
    published_at: datetime | None = None
    metric_name: str | None = None
    explicit_value: float | None = None
    explicit_unit: str | None = None
    task_class: str | None = None
    participant_segment: str | None = None
    caveats: list[str] | None = None
    quoted_finding: str | None = None
    tags: list[str] | None = None


@dataclass(frozen=True)
class _Metric:
    metric_name: str
    value: float
    unit: str
    text: str
    task_class: str | None
    participant_segment: str | None
    caveats: list[str]
    quoted_finding: str | None


class MetrProductivityReportsAdapter(SourceAdapter):
    """Read METR-style AI productivity and developer workflow reports."""

    config_keys = [
        "report_urls",
        "local_paths",
        "sections",
        "keywords",
        "metric_names",
        "max_items",
        "format",
    ]
    required_keys: list[str] = []
    description = (
        "Reads METR-style AI productivity and developer workflow Markdown and JSON "
        "reports as measured productivity evidence signals."
    )

    @property
    def name(self) -> str:
        return "metr_productivity_reports"

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
    def metric_names(self) -> list[str]:
        return _string_list(self._config.get("metric_names"))

    @property
    def format(self) -> str:
        value = str(self._config.get("format", "auto")).strip().lower()
        return value if value in {"auto", "json", "markdown", "md"} else "auto"

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
                f"Unable to read METR productivity report: {local_path}",
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
        for chunk in _parse_report_chunks(
            text,
            source_label=source_label,
            source_url=source_url,
            configured_format=self.format,
        ):
            if len(signals) >= limit:
                break
            if not _matches_any(chunk.section, self.sections):
                continue
            searchable = " ".join([chunk.report_title, chunk.section, chunk.text])
            matched_keywords = _matched_terms(searchable, self.keywords)
            if self.keywords and not matched_keywords:
                continue

            for metric in _extract_metrics(chunk, adapter_name=self.name):
                if len(signals) >= limit:
                    break
                matched_metrics = _matched_terms(
                    " ".join([metric.metric_name, metric.text]),
                    self.metric_names,
                )
                if self.metric_names and not matched_metrics:
                    continue
                signal = _signal_from_metric(
                    metric,
                    chunk,
                    adapter_name=self.name,
                    matched_keywords=matched_keywords,
                    matched_metric_names=matched_metrics,
                )
                if signal.id in seen:
                    continue
                seen.add(signal.id)
                signals.append(signal)


def _parse_report_chunks(
    text: str,
    *,
    source_label: str,
    source_url: str,
    configured_format: str,
) -> list[_ReportChunk]:
    stripped = text.lstrip()
    if configured_format == "json" or (
        configured_format == "auto" and _looks_like_json(source_label, stripped)
    ):
        return _parse_json_chunks(_parse_json(stripped, source_label), source_label, source_url)
    return _parse_markdown_chunks(text, source_label=source_label, source_url=source_url)


def _parse_markdown_chunks(text: str, *, source_label: str, source_url: str) -> list[_ReportChunk]:
    report_title = (
        _extract_markdown_title(text)
        or Path(urlparse(source_label).path).stem
        or "METR productivity report"
    )
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
        if not text or not _contains_metric(text):
            continue
        for fragment in _metric_fragments(text):
            chunks.append(
                _ReportChunk(
                    report_title=report_title,
                    section=section,
                    text=fragment,
                    source_label=source_label,
                    source_url=source_url,
                    url=source_url,
                    published_at=_published_from_source(source_label),
                    metric_name=_derive_metric_name(fragment),
                    task_class=_infer_task_class(fragment),
                    participant_segment=_infer_participant_segment(fragment),
                    caveats=_extract_caveats(fragment),
                    quoted_finding=_extract_quote(fragment),
                )
            )


def _parse_json_chunks(data: Any, source_label: str, source_url: str) -> list[_ReportChunk]:
    if not isinstance(data, (dict, list)):
        return []
    report_title = "METR productivity report"
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
    metric_name = _first_text(value, _METRIC_KEYS)
    task_class = _first_text(value, _TASK_CLASS_KEYS)
    participant_segment = _first_text(value, _SEGMENT_KEYS)
    explicit_value = _parse_float(_first_present(value, _VALUE_KEYS))
    explicit_unit = _normalize_unit(_first_text(value, _UNIT_KEYS))
    content = _first_text(value, _CONTENT_KEYS)
    caveats = _string_list(_first_present(value, _CAVEAT_KEYS))
    quoted_finding = _first_text(value, ("quoted_finding", "quote"))
    tags = _tags_from_json(value)

    text = _json_metric_text(metric_name, content, explicit_value, explicit_unit, caveats)
    if text and (explicit_value is not None or _contains_metric(text)):
        chunks.append(
            _ReportChunk(
                report_title=item_title or report_title,
                section=item_section,
                text=text,
                source_label=source_label,
                source_url=source_url,
                url=item_url,
                published_at=item_date,
                metric_name=metric_name or _derive_metric_name(text),
                explicit_value=explicit_value,
                explicit_unit=explicit_unit,
                task_class=task_class or _infer_task_class(text),
                participant_segment=participant_segment or _infer_participant_segment(text),
                caveats=caveats or _extract_caveats(text),
                quoted_finding=quoted_finding or _extract_quote(text),
                tags=tags,
            )
        )
    elif metric_name or content or explicit_value is not None:
        logger.warning(
            "metr_productivity_reports: skipping malformed metric row from %s",
            source_label,
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


def _extract_metrics(chunk: _ReportChunk, *, adapter_name: str) -> list[_Metric]:
    if chunk.explicit_value is not None and chunk.explicit_unit:
        return [
            _Metric(
                metric_name=chunk.metric_name or _derive_metric_name(chunk.text),
                value=chunk.explicit_value,
                unit=chunk.explicit_unit,
                text=chunk.text,
                task_class=chunk.task_class,
                participant_segment=chunk.participant_segment,
                caveats=chunk.caveats or [],
                quoted_finding=chunk.quoted_finding,
            )
        ]
    if chunk.explicit_value is not None and not chunk.explicit_unit:
        logger.warning("%s: skipping metric without unit from %s", adapter_name, chunk.source_label)
        return []

    metrics: list[_Metric] = []
    for match in _PERCENT_RE.finditer(chunk.text):
        value = float(match.group("value"))
        sign = match.group("sign")
        if sign == "-":
            value = -value
        unit = "delta_percent" if sign or _looks_like_delta(chunk.text, match.start()) else "percent"
        metrics.append(_metric_from_text(chunk, value=value, unit=unit))

    for match in _MULTIPLIER_RE.finditer(chunk.text):
        value = float(match.group("value"))
        metrics.append(_metric_from_text(chunk, value=value, unit="multiplier"))

    if chunk.metric_name and not metrics:
        logger.warning("%s: skipping metric row without parseable value from %s", adapter_name, chunk.source_label)
    return metrics


def _metric_from_text(chunk: _ReportChunk, *, value: float, unit: str) -> _Metric:
    return _Metric(
        metric_name=chunk.metric_name or _derive_metric_name(chunk.text),
        value=value,
        unit=unit,
        text=chunk.text,
        task_class=chunk.task_class,
        participant_segment=chunk.participant_segment,
        caveats=chunk.caveats or [],
        quoted_finding=chunk.quoted_finding,
    )


def _signal_from_metric(
    metric: _Metric,
    chunk: _ReportChunk,
    *,
    adapter_name: str,
    matched_keywords: list[str],
    matched_metric_names: list[str],
) -> Signal:
    title = f"{metric.metric_name}: {_format_number(metric.value)}{_unit_suffix(metric.unit)}"
    metadata = {
        "metric_name": metric.metric_name,
        "value": metric.value,
        "unit": metric.unit,
        "task_class": metric.task_class,
        "participant_segment": metric.participant_segment,
        "caveats": metric.caveats,
        "quoted_finding": metric.quoted_finding,
        "section": chunk.section,
        "report_title": chunk.report_title,
        "signal_role": "productivity",
        "metric_text": metric.text,
        "matched_keywords": matched_keywords,
        "matched_metric_names": matched_metric_names,
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
            metric.metric_name,
            metric.text,
            metric.unit,
            metric.value,
        ),
        source_type=SignalSourceType.REPORT,
        source_adapter=adapter_name,
        title=title[:240],
        content=metric.text[:1200],
        url=chunk.url,
        author="METR Productivity Reports",
        published_at=published_at,
        tags=_tags_for_metric(metric, chunk, matched_keywords, matched_metric_names),
        credibility=_credibility(metric),
        metadata=metadata,
    )


def _json_metric_text(
    metric_name: str | None,
    content: str | None,
    explicit_value: float | None,
    explicit_unit: str | None,
    caveats: list[str],
) -> str:
    text_parts = [part for part in [metric_name, content] if part]
    if explicit_value is not None:
        rendered_value = _format_number(explicit_value)
        if explicit_unit in {"percent", "delta_percent"}:
            rendered_value = f"{rendered_value}%"
        elif explicit_unit == "multiplier":
            rendered_value = f"{rendered_value}x"
        text_parts.append(rendered_value)
    text_parts.extend(caveats)
    return _clean_text(" ".join(text_parts))


def _looks_like_json(source_label: str, stripped_text: str) -> bool:
    suffix = Path(urlparse(source_label).path or source_label).suffix.lower()
    return suffix in {".json", ".jsonl"} or stripped_text.startswith(("{", "["))


def _parse_json(text: str, source_label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceParseError(
            f"Malformed METR productivity JSON report: {source_label}",
            adapter_name="metr_productivity_reports",
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
        return _clean_text(" | ".join(cell for cell in cells if cell))
    text = re.sub(r"^\s*[-*+]\s+", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    return _clean_text(text)


def _metric_fragments(text: str) -> list[str]:
    fragments = [fragment.strip() for fragment in _SENTENCE_SPLIT_RE.split(text) if fragment.strip()]
    return [fragment for fragment in fragments if _contains_metric(fragment)] or [text]


def _contains_metric(text: str) -> bool:
    return bool(_PERCENT_RE.search(text) or _MULTIPLIER_RE.search(text))


def _looks_like_delta(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - 50) : match_start + 90].lower()
    return any(
        term in window
        for term in (
            "increase",
            "increased",
            "decrease",
            "decreased",
            "delta",
            "change",
            "faster",
            "slower",
            "speedup",
            "slowdown",
            "productivity",
            "completion time",
            "time to complete",
        )
    )


def _derive_metric_name(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" -:|.")
    if "|" in cleaned:
        first_cell = cleaned.split("|", maxsplit=1)[0].strip(" -:|.")
        if first_cell:
            return first_cell[:120]
    cleaned = _PERCENT_RE.sub("", cleaned)
    cleaned = _MULTIPLIER_RE.sub("", cleaned)
    leading = re.split(
        r"\b(?:was|were|is|are|reached|changed|showed|reported)\b",
        cleaned,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" -:|.")
    if 3 <= len(leading) <= 80:
        return leading
    cleaned = re.sub(
        r"\b(value|rate|share|increase|decrease|finding|caveat|reported)\b",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:|.")
    return cleaned[:120] or "Measured productivity delta"


def _infer_task_class(text: str) -> str | None:
    lowered = text.lower()
    if "real-world" in lowered or "real world" in lowered:
        return "real-world engineering tasks"
    if "issue" in lowered:
        return "issue resolution"
    if "debug" in lowered:
        return "debugging"
    if "workflow" in lowered:
        return "developer workflow"
    if "review" in lowered:
        return "code review"
    return None


def _infer_participant_segment(text: str) -> str | None:
    lowered = text.lower()
    if "experienced developer" in lowered or "experienced open-source" in lowered:
        return "experienced developers"
    if "developer" in lowered:
        return "developers"
    if "participant" in lowered:
        return "participants"
    if "team" in lowered:
        return "teams"
    return None


def _extract_caveats(text: str) -> list[str]:
    fragments = _SENTENCE_SPLIT_RE.split(text)
    caveats: list[str] = []
    for fragment in fragments:
        lowered = fragment.lower()
        if any(term in lowered for term in ("caveat", "limitation", "confidence", "not causal")):
            caveats.append(_clean_text(fragment))
    return caveats


def _extract_quote(text: str) -> str | None:
    match = _QUOTE_RE.search(text)
    if match:
        return _clean_text(match.group(1))
    return None


def _credibility(metric: _Metric) -> float:
    if metric.caveats:
        return 0.83
    if metric.unit == "delta_percent":
        return 0.86
    return 0.8


def _tags_for_metric(
    metric: _Metric,
    chunk: _ReportChunk,
    matched_keywords: list[str],
    matched_metric_names: list[str],
) -> list[str]:
    tags = ["metr", "productivity", "ai-code", "report", metric.unit, metric.metric_name]
    tags.extend(chunk.tags or [])
    tags.extend(_slug_tokens(chunk.section))
    tags.extend(matched_keywords)
    tags.extend(matched_metric_names)
    if metric.task_class:
        tags.append(metric.task_class)
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


def _tags_from_json(value: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for key in _TAG_KEYS:
        tags.extend(_string_list(_first_present(value, (key,))))
    return tags


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _slug_tokens(value: str) -> list[str]:
    slug = _slug(value)
    return [part for part in slug.split("-") if len(part) > 2][:4]


def _parse_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    percent = _PERCENT_RE.search(text)
    if percent:
        parsed = float(percent.group("value"))
        return -parsed if percent.group("sign") == "-" else parsed
    multiplier = _MULTIPLIER_RE.search(text)
    if multiplier:
        return float(multiplier.group("value"))
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_unit(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"%", "percent", "percentage", "share"}:
        return "percent"
    if lowered in {"delta_percent", "percentage_point", "percentage points", "pp"}:
        return "delta_percent"
    if lowered in {"x", "multiplier", "multiple"}:
        return "multiplier"
    if "percent" in lowered and any(term in lowered for term in ("delta", "change", "point")):
        return "delta_percent"
    if "percent" in lowered:
        return "percent"
    return None


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


def _extract_year(value: str) -> int | None:
    match = _YEAR_RE.search(value)
    return int(match.group(1)) if match else None


def _published_from_source(source_label: str) -> datetime | None:
    year = _extract_year(source_label)
    if year is None:
        return None
    return datetime(year, 1, 1, tzinfo=timezone.utc)


def _file_url(local_path: str) -> str:
    return f"file://{Path(local_path).resolve()}"


def _unit_suffix(unit: str) -> str:
    if unit in {"percent", "delta_percent"}:
        return "%"
    if unit == "multiplier":
        return "x"
    return ""


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _stable_id(
    adapter_name: str,
    source_url: str,
    section: str,
    metric_name: str,
    text: str,
    unit: str,
    value: float,
) -> str:
    raw = "\x1f".join([source_url, section, metric_name, text, unit, _format_number(value)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{adapter_name}:{digest}"
