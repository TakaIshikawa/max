"""Small helpers shared by compact API JSON renderers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


def mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def strings(value: Any) -> list[str]:
    return sorted({str(item) for item in as_list(value) if item not in (None, "")})


def int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def float_or_zero(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def rounded(value: Any, digits: int = 2) -> float:
    return round(float_or_zero(value), digits)


def bool_or_default(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def datetime_to_string(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def age_bucket(value: Any, as_of: datetime | None) -> str:
    created_at = parse_datetime(value)
    if created_at is None or as_of is None:
        return "unknown"
    days = max((as_of - created_at).days, 0)
    if days <= 1:
        return "0_1d"
    if days <= 7:
        return "2_7d"
    if days <= 30:
        return "8_30d"
    return "over_30d"


def source_metadata(payload: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    metadata = dict(mapping(payload.get("metadata")))
    return {
        **metadata,
        "source_schema_version": metadata.get("source_schema_version")
        or payload.get("schema_version"),
        "source_kind": metadata.get("source_kind") or payload.get("kind"),
        **extra,
    }
