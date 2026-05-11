"""App store review import adapter."""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

_ALIASES = {
    "reviewer": ["reviewer", "author", "user", "username", "name"],
    "rating": ["rating", "stars", "score"],
    "title": ["title", "subject", "headline"],
    "body": ["body", "review", "content", "text", "comment"],
    "version": ["version", "app_version", "release"],
    "country": ["country", "locale", "region"],
    "reviewed_at": ["reviewed_at", "date", "created_at", "published_at"],
    "helpful_count": ["helpful_count", "helpful", "votes", "thumbs_up"],
}


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _resolve(headers: list[str], field: str) -> str | None:
    lower = {header.strip().lower(): header for header in headers}
    return next((lower[alias] for alias in _ALIASES[field] if alias in lower), None)


def _number(value: object) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int:
    parsed = _number(value)
    return int(parsed) if parsed is not None else 0


def _parse_dt(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_item(item: dict) -> dict | None:
    row = {
        field: _text(item.get(field) or next((_text(item.get(alias)) for alias in aliases if _text(item.get(alias))), ""))
        for field, aliases in _ALIASES.items()
    }
    if not row["body"] and not row["title"]:
        return None
    rating = _number(row["rating"])
    if rating is None:
        return None
    row["rating"] = rating
    row["helpful_count"] = _int(row["helpful_count"])
    return row


def parse_csv_reviews(content: str) -> list[dict]:
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


def parse_json_reviews(content: str) -> list[dict]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in app store review data")
        return []
    return normalize_review_items(data)


def normalize_review_items(data: object) -> list[dict]:
    if isinstance(data, dict):
        items = data.get("reviews") or data.get("data") or data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        return []
    return [row for item in items if isinstance(item, dict) for row in [_normalize_item(item)] if row]


class AppStoreReviewsAdapter(SourceAdapter):
    """Convert app marketplace reviews into normalized feedback signals."""

    @property
    def name(self) -> str:
        return "app_store_reviews"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKETPLACE.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0:
            return []
        rows: list[dict] = []
        for file_path in self._config.get("files", []) if isinstance(self._config.get("files", []), list) else []:
            try:
                path = Path(file_path)
                content = path.read_text(encoding="utf-8")
            except Exception:
                logger.warning("Failed to read app store review file: %s", file_path, exc_info=True)
                continue
            rows.extend(parse_csv_reviews(content) if path.suffix.lower() == ".csv" else parse_json_reviews(content))
        rows.extend(normalize_review_items(self._config.get("data")))
        return [signal for row in rows if (signal := self._row_to_signal(row)) is not None][:limit]

    def _row_to_signal(self, row: dict) -> Signal | None:
        min_rating = _number(self._config.get("min_rating"))
        max_rating = _number(self._config.get("max_rating"))
        rating = row["rating"]
        if min_rating is not None and rating < min_rating:
            return None
        if max_rating is not None and rating > max_rating:
            return None
        app_name = _text(self._config.get("app_name"))
        marketplace = _text(self._config.get("marketplace"))
        tags = {"app_store_review", "positive" if rating >= 4 else "negative" if rating <= 2 else "neutral"}
        tags.update(_text(tag).lower() for tag in self._config.get("tags", []) if _text(tag))
        if marketplace:
            tags.add(marketplace.lower().replace(" ", "_"))
        body = row["body"]
        title = row["title"] or body[:80] or "App store review"
        return Signal(
            source_type=SignalSourceType.MARKETPLACE,
            source_adapter=self.name,
            title=f"{app_name}: {title}" if app_name else title,
            content=body or title,
            url="",
            author=row["reviewer"] or None,
            published_at=_parse_dt(row["reviewed_at"]),
            tags=sorted(tags),
            credibility=max(0.2, min((rating / 5) * 0.6 + min(row["helpful_count"], 20) / 50, 1.0)),
            metadata={
                "app_name": app_name,
                "marketplace": marketplace,
                "reviewer": row["reviewer"],
                "rating": rating,
                "title": row["title"],
                "body": body,
                "version": row["version"],
                "country": row["country"],
                "reviewed_at": row["reviewed_at"],
                "helpful_count": row["helpful_count"],
            },
        )
