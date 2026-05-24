"""JSON API renderer for source adapter schema status."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.api.source_adapter_schema_status.v1"
KIND = "max.api.source_adapter_schema_status"
STATUS_RANK = {"incompatible": 0, "drifted": 1, "unknown": 2, "compatible": 3}


def source_adapter_schema_status_to_json(payload: Mapping[str, Any], *, as_of: str | datetime | None = None) -> str:
    adapters = _adapters(payload)
    normalized = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": _summary(adapters),
        "adapters": adapters,
        "incompatible_adapters": [row for row in adapters if row["status"] == "incompatible"],
        "source_totals": _totals(adapters, "source"),
        "schema_totals": _totals(adapters, "expected_schema_version"),
        "metadata": _metadata(payload, adapters, as_of),
    }
    return json.dumps(normalized, indent=2, sort_keys=True)


def _adapters(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = payload.get("adapters") if isinstance(payload.get("adapters"), list) else payload.get("schemas")
    rows = [_adapter(item, index) for index, item in enumerate(source if isinstance(source, list) else [], start=1) if isinstance(item, Mapping)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["source"], row["adapter"]))
    return rows


def _adapter(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    missing_fields = _strings(item.get("missing_fields") or item.get("missing"))
    extra_fields = _strings(item.get("extra_fields") or item.get("extra"))
    compatibility = _compatibility(item.get("compatibility"))
    expected = _text(item.get("expected_schema_version") or item.get("expected")) or "unknown-schema"
    observed = _text(item.get("observed_schema_version") or item.get("observed")) or "unknown-schema"
    status = _status(compatibility, expected, observed, missing_fields, extra_fields)
    return {
        "adapter": _text(item.get("adapter") or item.get("adapter_name")) or f"adapter-{index}",
        "source": _text(item.get("source") or item.get("source_name")) or "unknown-source",
        "expected_schema_version": expected,
        "observed_schema_version": observed,
        "missing_fields": missing_fields,
        "extra_fields": extra_fields,
        "compatibility": compatibility,
        "status": status,
    }


def _status(compatibility: str, expected: str, observed: str, missing_fields: list[str], extra_fields: list[str]) -> str:
    if compatibility == "incompatible" or missing_fields:
        return "incompatible"
    if compatibility == "drifted" or expected != observed or extra_fields:
        return "drifted"
    if compatibility == "unknown" or "unknown-schema" in {expected, observed}:
        return "unknown"
    return "compatible"


def _summary(adapters: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["status"] for row in adapters)
    return {"adapter_count": len(adapters), "compatible_count": counts["compatible"], "drifted_count": counts["drifted"], "incompatible_count": counts["incompatible"], "unknown_count": counts["unknown"]}


def _totals(adapters: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in adapters:
        grouped[row[field]].append(row)
    return [{field: key, "adapter_count": len(items), "incompatible_count": sum(1 for item in items if item["status"] == "incompatible")} for key, items in sorted(grouped.items())]


def _metadata(payload: Mapping[str, Any], adapters: list[dict[str, Any]], as_of: str | datetime | None) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {})
    return {**metadata, "source_schema_version": payload.get("schema_version"), "source_kind": payload.get("kind"), "as_of": _as_of(as_of), "adapter_count": len(adapters)}


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
    return sorted({str(item).strip() for item in values if item not in (None, "")})


def _compatibility(value: Any) -> str:
    text = _text(value).lower().replace(" ", "_")
    return text if text in {"compatible", "drifted", "incompatible", "unknown"} else "unknown"


def _as_of(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
