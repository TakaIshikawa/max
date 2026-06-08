"""Source adapter schema compatibility export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_schema_compatibility_report.v1"
KIND = "max.source_adapter_schema_compatibility_report"
_STATUS_RANK = {"incompatible": 0, "warning": 1, "compatible": 2}


def generate_source_adapter_schema_compatibility_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, dict):
            continue
        adapter = _text(raw.get("adapter") or raw.get("adapter_name") or raw.get("name")) or f"adapter-{index}"
        source = _text(raw.get("source") or raw.get("source_name") or raw.get("source_id")) or "unknown-source"
        required = _fields(raw.get("required_fields") or raw.get("expected_fields") or raw.get("schema_fields"))
        provided = _fields(raw.get("provided_fields") or raw.get("payload_fields") or raw.get("observed_fields"))
        deprecated = _fields(raw.get("deprecated_fields"))
        type_mismatches = sorted(_fields(raw.get("type_mismatches") or raw.get("incompatible_fields")), key=str.lower)
        missing = sorted(required - provided, key=str.lower)
        extra_deprecated = sorted(provided & deprecated, key=str.lower)
        status = "incompatible" if missing or type_mismatches else ("warning" if extra_deprecated else "compatible")
        rows.append({"adapter": adapter, "source": source, "required_field_count": len(required), "provided_field_count": len(provided), "missing_fields": missing, "deprecated_fields": extra_deprecated, "type_mismatches": type_mismatches, "status": status})
    rows.sort(key=lambda row: (_STATUS_RANK[row["status"]], row["adapter"].casefold(), row["source"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "incompatible_count": sum(1 for row in rows if row["status"] == "incompatible"), "warning_count": sum(1 for row in rows if row["status"] == "warning"), "compatible_count": sum(1 for row in rows if row["status"] == "compatible")}, "rows": rows}


def _fields(value: Any) -> set[str]:
    if isinstance(value, dict):
        items = value.keys()
    elif isinstance(value, str):
        items = [value]
    elif isinstance(value, list | tuple | set):
        items = value
    else:
        items = []
    return {_text(item) for item in items if _text(item)}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
