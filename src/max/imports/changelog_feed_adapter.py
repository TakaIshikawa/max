"""Changelog feed import adapter."""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime
from pathlib import Path

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_ALIASES = {
    "version": ["version", "release", "tag"],
    "date": ["date", "released_at", "published_at", "created_at"],
    "title": ["title", "name", "headline"],
    "summary": ["summary", "description", "body", "notes"],
    "category": ["category", "type", "kind"],
    "url": ["url", "link", "html_url"],
    "breaking_change": ["breaking_change", "breaking", "is_breaking"],
    "affected_features": ["affected_features", "features", "components", "areas"],
}


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _resolve(headers: list[str], field: str) -> str | None:
    lower = {header.strip().lower(): header for header in headers}
    return next((lower[alias] for alias in _ALIASES[field] if alias in lower), None)


def _bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "breaking"}


def _features(value: object) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]


def _normalize_item(item: dict) -> dict | None:
    row = {
        field: item.get(field) if field in item else next((item.get(alias) for alias in aliases if alias in item), "")
        for field, aliases in _ALIASES.items()
    }
    if not _text(row["title"]) and not _text(row["summary"]) and not _text(row["version"]):
        return None
    row["affected_features"] = _features(row["affected_features"])
    row["breaking_change"] = _bool(row["breaking_change"])
    return row


def parse_csv_changelog(content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return []
    columns = {field: _resolve(list(reader.fieldnames), field) for field in _ALIASES}
    rows = []
    for raw in reader:
        normalized = _normalize_item({field: raw.get(column, "") if column else "" for field, column in columns.items()})
        if normalized:
            rows.append(normalized)
    return rows


def parse_json_changelog(content: str) -> list[dict]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in changelog data")
        return []
    return normalize_changelog_items(data)


def parse_jsonl_changelog(content: str) -> list[dict]:
    rows = []
    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and (normalized := _normalize_item(item)):
            rows.append(normalized)
    return rows


def normalize_changelog_items(data: object) -> list[dict]:
    if isinstance(data, dict):
        items = data.get("entries") or data.get("releases") or data.get("data") or data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        return []
    return [row for item in items if isinstance(item, dict) for row in [_normalize_item(item)] if row]


class ChangelogFeedAdapter(SourceAdapter):
    """Turn product changelog entries into roadmap signals."""

    @property
    def name(self) -> str:
        return "changelog_feed"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []
        rows: list[dict] = []
        for file_path in self._config.get("files", []) if isinstance(self._config.get("files", []), list) else []:
            try:
                path = Path(file_path)
                content = path.read_text(encoding="utf-8")
            except Exception:
                logger.warning("Failed to read changelog file: %s", file_path, exc_info=True)
                continue
            suffix = path.suffix.lower()
            if suffix == ".csv":
                rows.extend(parse_csv_changelog(content))
            elif suffix == ".jsonl":
                rows.extend(parse_jsonl_changelog(content))
            elif suffix == ".json":
                rows.extend(parse_json_changelog(content))
        rows.extend(normalize_changelog_items(self._config.get("data")))
        return [signal for row in rows if (signal := self._row_to_signal(row)) is not None][:limit]

    def _row_to_signal(self, row: dict) -> Signal | None:
        since = _text(self._config.get("since"))
        date = _text(row.get("date"))
        if since and date and date < since:
            return None
        product = _text(self._config.get("product_name"))
        vendor = _text(self._config.get("vendor"))
        version = _text(row.get("version"))
        category = _text(row.get("category"))
        title = _text(row.get("title")) or f"{product} {version}".strip() or "Changelog entry"
        summary = _text(row.get("summary"))
        features = row.get("affected_features") if isinstance(row.get("affected_features"), list) else []
        tags = {"changelog", "roadmap"}
        tags.update(_text(tag).lower() for tag in self._config.get("tags", []) if _text(tag))
        if category:
            tags.add(category.lower().replace(" ", "_"))
        if row.get("breaking_change"):
            tags.add("breaking_change")
        return Signal(
            source_type=SignalSourceType.ROADMAP,
            source_adapter=self.name,
            title=f"{product}: {title}" if product else title,
            content=summary or title,
            url=_text(row.get("url")) or _text(self._config.get("default_url")),
            published_at=_parse_date(date),
            tags=sorted(tags),
            credibility=0.7,
            metadata={
                "product_name": product,
                "vendor": vendor,
                "version": version,
                "date": date,
                "category": category,
                "breaking_change": bool(row.get("breaking_change")),
                "affected_features": features,
                "url": _text(row.get("url")) or _text(self._config.get("default_url")),
            },
        )


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
