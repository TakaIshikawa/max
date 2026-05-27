"""JSON API renderer for profile weight override status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from max.api._renderer_utils import datetime_to_string, float_or_zero, parse_datetime, source_metadata

SCHEMA_VERSION = "max.api.profile_weight_override_status.v1"
KIND = "max.api.profile_weight_override_status"


def profile_weight_override_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    checked_at = parse_datetime(as_of)
    rows = _rows(payload, checked_at)
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "rows": rows, "metadata": source_metadata(payload, as_of=datetime_to_string(checked_at), override_count=len(rows))}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _rows(payload: Mapping[str, Any], as_of: datetime | None) -> list[dict[str, Any]]:
    source = payload.get("overrides") if isinstance(payload.get("overrides"), list) else payload.get("items")
    rows = [_row(item, as_of) for item in source if isinstance(item, Mapping)] if isinstance(source, list) else []
    return sorted(rows, key=lambda row: (not row["expired"], not row["unapproved"], row["profile"], row["dimension"]))


def _row(item: Mapping[str, Any], as_of: datetime | None) -> dict[str, Any]:
    base = float_or_zero(item.get("base_weight"))
    override = float_or_zero(item.get("override_weight"))
    expires_at = parse_datetime(item.get("expires_at"))
    drift = abs(override - base)
    return {"profile": _bucket(item.get("profile"), "default"), "dimension": _bucket(item.get("dimension"), "overall"), "base_weight": round(base, 4), "override_weight": round(override, 4), "source": _bucket(item.get("source"), "manual"), "expires_at": datetime_to_string(expires_at), "approved_by": _text(item.get("approved_by")) or None, "absolute_drift": round(drift, 4), "relative_drift": round(drift / abs(base), 4) if base else (1.0 if drift else 0.0), "expired": bool(as_of and expires_at and expires_at < as_of), "unapproved": not bool(_text(item.get("approved_by")))}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "attention" if any(row["expired"] or row["unapproved"] for row in rows) else "active", "active_override_count": sum(1 for row in rows if not row["expired"]), "expired_override_count": sum(1 for row in rows if row["expired"]), "unapproved_override_count": sum(1 for row in rows if row["unapproved"])}


def _bucket(value: Any, default: str) -> str:
    return (_text(value) or default).lower().replace(" ", "_")


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
