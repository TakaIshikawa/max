"""Glama MCP ecosystem stats source adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import re
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
_JSON_CONTAINER_KEYS = (
    "metrics",
    "stats",
    "summary",
    "categories",
    "category_stats",
    "trust",
    "funding",
    "adoption",
    "downloads",
    "data",
    "items",
    "results",
)
_CATEGORY_KEYS = ("category", "name", "label", "segment", "type")
_METRIC_NAME_KEYS = ("metric_name", "metric", "name", "label")
_METRIC_VALUE_KEYS = ("metric_value", "value", "count", "total", "amount")
_DATE_KEYS = ("snapshot_date", "date", "report_date", "updated_at", "updatedAt")
_SOURCE_URL_KEYS = ("source_url", "url", "canonical_url", "link")
_COUNT_KEYS = ("server_count", "servers", "count", "total_servers", "total")
_NON_METRIC_KEYS = {
    "category",
    "name",
    "label",
    "segment",
    "type",
    "snapshot_date",
    "date",
    "report_date",
    "updated_at",
    "updatedat",
    "source_url",
    "url",
    "canonical_url",
    "link",
    "notes",
    "description",
}
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


class GlamaMcpStatsAdapter(SourceAdapter):
    """Read Glama-style MCP ecosystem aggregate stats from JSON or Markdown reports."""

    @property
    def name(self) -> str:
        return "glama_mcp_stats"

    @property
    def source_type(self) -> str:
        return SignalSourceType.REPORT.value

    @property
    def stats_urls(self) -> list[str]:
        return _string_list(self._config.get("stats_urls"))

    @property
    def local_paths(self) -> list[str]:
        return _string_list(self._config.get("local_paths"))

    @property
    def categories(self) -> list[str]:
        return _string_list(self._config.get("categories"))

    @property
    def min_server_count(self) -> int:
        return _parse_int(self._config.get("min_server_count")) or 0

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

        if len(signals) < item_limit and self.stats_urls:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for stats_url in self.stats_urls:
                    if len(signals) >= item_limit:
                        break
                    text = await self._fetch_stats_url(stats_url, client)
                    if text is None:
                        continue
                    self._append_signals(
                        signals,
                        text,
                        source_label=stats_url,
                        source_url=stats_url,
                        limit=item_limit,
                        seen=seen,
                    )

        return signals[:item_limit]

    def _read_local_path(self, local_path: str) -> str:
        try:
            return Path(local_path).read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise SourceParseError(
                f"Unable to read Glama MCP stats report: {local_path}",
                adapter_name=self.name,
            ) from exc

    async def _fetch_stats_url(self, stats_url: str, client: httpx.AsyncClient) -> str | None:
        try:
            response = await fetch_with_retry(stats_url, client, adapter_name=self.name)
        except AdapterFetchError as exc:
            logger.warning("%s: failed to fetch stats URL %s: %s", self.name, stats_url, exc)
            return None
        except Exception as exc:
            logger.warning("%s: failed to fetch stats URL %s: %s", self.name, stats_url, exc)
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
        for row in _parse_rows(text, source_label=source_label):
            if len(signals) >= limit:
                break
            signal = _signal_from_row(
                row,
                adapter_name=self.name,
                default_source_url=source_url,
                category_filters=self.categories,
                min_server_count=self.min_server_count,
            )
            if signal is None or signal.id in seen:
                continue
            seen.add(signal.id)
            signals.append(signal)


def _parse_rows(text: str, *, source_label: str) -> list[dict[str, Any]]:
    stripped = text.lstrip()
    if _looks_like_json(source_label, stripped):
        return _extract_json_rows(_parse_json(stripped, source_label))
    return _parse_markdown_tables(text)


def _looks_like_json(source_label: str, stripped_text: str) -> bool:
    suffix = Path(urlparse(source_label).path or source_label).suffix.lower()
    return suffix in {".json", ".jsonl"} or stripped_text.startswith(("{", "["))


def _parse_json(text: str, source_label: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceParseError(
            f"Malformed Glama MCP stats JSON report: {source_label}",
            adapter_name="glama_mcp_stats",
        ) from exc


def _extract_json_rows(data: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    _collect_json_rows(data, rows, context={})
    return rows


def _collect_json_rows(data: Any, rows: list[dict[str, Any]], *, context: dict[str, Any]) -> None:
    if isinstance(data, list):
        for item in data:
            _collect_json_rows(item, rows, context=context)
        return

    if not isinstance(data, dict):
        return

    inherited = {
        key: data[key]
        for key in (*_DATE_KEYS, *_SOURCE_URL_KEYS)
        if key in data and not isinstance(data[key], (dict, list))
    }
    current_context = {**context, **inherited}

    if _is_metric_row(data):
        rows.extend(_rows_from_mapping(data, current_context))

    for key in _JSON_CONTAINER_KEYS:
        value = data.get(key)
        if value is None:
            continue
        child_context = current_context
        if key in {"categories", "category_stats"}:
            child_context = {**child_context, "signal_role": "market"}
        elif key in {"trust", "funding", "adoption", "downloads"}:
            child_context = {**child_context, "signal_role": key}
        _collect_json_rows(value, rows, context=child_context)


def _rows_from_mapping(data: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    metric_name = _first_text(data, _METRIC_NAME_KEYS)
    metric_value = _first_number(data, _METRIC_VALUE_KEYS)
    category = _first_text(data, _CATEGORY_KEYS)

    if metric_name and metric_value is not None:
        return [{**context, **data, "metric_name": metric_name, "metric_value": metric_value}]

    rows: list[dict[str, Any]] = []
    for key, value in data.items():
        normalized_key = _normalize_key(key)
        if normalized_key in _NON_METRIC_KEYS or isinstance(value, (dict, list)):
            continue
        parsed = _parse_number(value)
        if parsed is None:
            continue
        rows.append(
            {
                **context,
                **data,
                "metric_name": key,
                "metric_value": parsed,
                "category": category,
            }
        )
    return rows


def _is_metric_row(data: dict[str, Any]) -> bool:
    if _first_number(data, _METRIC_VALUE_KEYS) is not None and _first_text(data, _METRIC_NAME_KEYS):
        return True
    return any(
        _normalize_key(key) not in _NON_METRIC_KEYS
        and not isinstance(value, (dict, list))
        and _parse_number(value) is not None
        for key, value in data.items()
    )


def _parse_markdown_tables(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines) - 1:
        header_line = lines[index]
        separator_line = lines[index + 1]
        if "|" not in header_line or not _TABLE_SEPARATOR_RE.match(separator_line):
            index += 1
            continue

        headers = [_normalize_header(cell) for cell in _split_table_row(header_line)]
        index += 2
        while index < len(lines) and "|" in lines[index] and lines[index].strip():
            cells = _split_table_row(lines[index])
            if len(cells) == len(headers):
                row = {headers[pos]: _clean_text(cell) for pos, cell in enumerate(cells)}
                rows.extend(_rows_from_mapping(row, {}))
            index += 1
    return rows


def _signal_from_row(
    row: dict[str, Any],
    *,
    adapter_name: str,
    default_source_url: str,
    category_filters: list[str],
    min_server_count: int,
) -> Signal | None:
    metric_name = _first_text(row, _METRIC_NAME_KEYS)
    metric_value = _first_number(row, _METRIC_VALUE_KEYS)
    if not metric_name or metric_value is None:
        return None

    category = _first_text(row, _CATEGORY_KEYS)
    if category and not _matches_any(category, category_filters):
        return None

    server_count = _server_count_for_row(row, metric_name, metric_value)
    if min_server_count > 0 and server_count is not None and server_count < min_server_count:
        return None

    source_url = _first_text(row, _SOURCE_URL_KEYS) or default_source_url
    snapshot_date = _first_text(row, _DATE_KEYS)
    published_at = _parse_datetime(snapshot_date)
    normalized_metric_name = _humanize(metric_name)
    display_value = _format_number(metric_value)
    title = (
        f"Glama MCP {category} {normalized_metric_name}: {display_value}"
        if category
        else f"Glama MCP {normalized_metric_name}: {display_value}"
    )
    content_parts = [
        f"{normalized_metric_name} is {display_value}",
        f"for {category}" if category else "across the MCP ecosystem",
    ]
    if snapshot_date:
        content_parts.append(f"as of {snapshot_date}")
    content = " ".join(content_parts) + "."

    signal_role = _first_text(row, ("signal_role",)) or _infer_signal_role(metric_name)
    metadata = {
        "metric_name": _slug(metric_name).replace("-", "_"),
        "metric_value": metric_value,
        "category": category,
        "snapshot_date": snapshot_date,
        "source_url": source_url,
        "signal_role": signal_role,
        "adapter_scope": "aggregate_ecosystem_stats",
    }

    return Signal(
        id=_stable_id(adapter_name, source_url, metric_name, category or "", str(metric_value)),
        source_type=SignalSourceType.REPORT,
        source_adapter=adapter_name,
        title=title[:240],
        content=content[:1200],
        url=source_url,
        author="Glama MCP Stats",
        published_at=published_at,
        tags=_build_tags(metric_name, category, signal_role),
        credibility=0.8,
        metadata=metadata,
    )


def _server_count_for_row(
    row: dict[str, Any],
    metric_name: str,
    metric_value: int | float,
) -> int | None:
    if _normalize_key(metric_name) in {_normalize_key(key) for key in _COUNT_KEYS}:
        return int(metric_value)
    for key in _COUNT_KEYS:
        value = _first_number(row, (key,))
        if value is not None:
            return int(value)
    return None


def _infer_signal_role(metric_name: str) -> str:
    normalized = _slug(metric_name)
    if any(term in normalized for term in ("fund", "invest", "revenue")):
        return "funding"
    if any(term in normalized for term in ("trust", "verified", "security")):
        return "trust"
    if any(term in normalized for term in ("download", "install", "adoption")):
        return "adoption"
    return "market"


def _build_tags(metric_name: str, category: str | None, signal_role: str) -> list[str]:
    tags = ["glama", "mcp", "stats", signal_role, *_slug_tokens(metric_name)]
    if category:
        tags.extend(_slug_tokens(category))
    seen: set[str] = set()
    normalized: list[str] = []
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


def _first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value = _first_present(row, keys)
    if value is None or isinstance(value, (dict, list)):
        return None
    text = _clean_text(str(value))
    return text or None


def _first_number(row: dict[str, Any], keys: tuple[str, ...]) -> int | float | None:
    value = _first_present(row, keys)
    return _parse_number(value)


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for key in keys:
        normalized_key = _normalize_key(key)
        if normalized_key in normalized:
            return normalized[normalized_key]
    return None


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


def _parse_int(value: object) -> int | None:
    parsed = _parse_number(value)
    return int(parsed) if parsed is not None else None


def _parse_number(value: object) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("$", "")
    multiplier = 1.0
    if text[-1:].lower() == "k":
        multiplier = 1_000.0
        text = text[:-1]
    elif text[-1:].lower() == "m":
        multiplier = 1_000_000.0
        text = text[:-1]
    elif text[-1:].lower() == "b":
        multiplier = 1_000_000_000.0
        text = text[:-1]
    text = text.strip().rstrip("%")
    try:
        parsed = float(text) * multiplier
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else parsed


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


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _normalize_header(value: str) -> str:
    return _slug(value).replace("-", "_")


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _humanize(value: str) -> str:
    return _clean_text(re.sub(r"[_-]+", " ", value)).title()


def _format_number(value: int | float) -> str:
    if isinstance(value, int) or value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _slug_tokens(value: str) -> list[str]:
    slug = _slug(value)
    return [part for part in slug.split("-") if len(part) > 2][:4]


def _file_url(local_path: str) -> str:
    return f"file://{Path(local_path).resolve()}"


def _stable_id(adapter_name: str, source_url: str, metric_name: str, category: str, value: str) -> str:
    raw = "\x1f".join([source_url, metric_name, category, value])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{adapter_name}:{digest}"
