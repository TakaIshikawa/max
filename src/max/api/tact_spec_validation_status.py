"""JSON API renderer for Tact spec validation status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.tact_spec_validation_status.v1"
KIND = "max.api.tact_spec_validation_status"
STATUS_RANK = {"invalid": 0, "warnings": 1, "valid": 2, "skipped": 3}


def tact_spec_validation_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    validations = _validations(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(validations),
        "validations": validations,
        "invalid_specs": [row for row in validations if row["status"] == "invalid"],
        "validator_totals": _validator_totals(validations),
        "missing_field_totals": _missing_field_totals(validations),
        "metadata": _metadata(payload, validations, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _validations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("validations") if isinstance(payload.get("validations"), list) else payload.get("specs")
    rows = [_validation(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["spec_id"], row["validator"]))
    return rows


def _validation(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    errors = _int(item.get("error_count", item.get("errors")))
    warnings = _int(item.get("warning_count", item.get("warnings")))
    missing_fields = _strings(item.get("missing_fields") or item.get("missing"))
    skipped = _bool(item.get("skipped")) or _text(item.get("status")).lower() == "skipped"
    status = "skipped" if skipped else ("invalid" if errors or missing_fields else ("warnings" if warnings else "valid"))
    return {
        "spec_id": _text(item.get("spec_id") or item.get("id")) or f"spec-{index}",
        "idea_id": _text(item.get("idea_id") or item.get("idea")) or "unknown-idea",
        "validator": _text(item.get("validator")) or "unknown-validator",
        "error_count": errors,
        "warning_count": warnings,
        "missing_fields": missing_fields,
        "schema_version": _text(item.get("schema_version")) or "unknown-schema",
        "status": status,
    }


def _summary(validations: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in validations)
    return {"validation_count": len(validations), "valid_count": counts["valid"], "warnings_count": counts["warnings"], "invalid_count": counts["invalid"], "skipped_count": counts["skipped"]}


def _validator_totals(validations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in validations:
        grouped[row["validator"]].append(row)
    return [{"validator": key, "validation_count": len(items), "invalid_count": sum(1 for item in items if item["status"] == "invalid")} for key, items in sorted(grouped.items())]


def _missing_field_totals(validations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter(field for row in validations for field in row["missing_fields"])
    return [{"field": field, "missing_count": count} for field, count in sorted(counts.items())]


def _metadata(payload: Mapping[str, Any], validations: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "validation_count": len(validations)}


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    return sorted({str(item).strip() for item in values if item not in (None, "")})


def _int(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "skipped"}
    return bool(value)


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
