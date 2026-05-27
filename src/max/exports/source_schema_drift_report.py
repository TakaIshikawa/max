"""Source schema drift export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_schema_drift_report.v1"
KIND = "max.source_schema_drift_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"
SEVERITY = {"missing_field": 0, "type_change": 1, "new_field": 2}


def build_source_schema_drift_report(
    records: Iterable[dict[str, Any]] | dict[str, Any],
    *,
    baseline: dict[str, dict[str, str]] | None = None,
    optional_allowlist: Iterable[str] = (),
    title: str = "Source Schema Drift Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    allow = set(optional_allowlist)
    observed = _observed(records)
    expected = baseline or _baseline(records)
    rows = []
    for source in sorted(set(expected) | set(observed), key=str.lower):
        exp_fields = expected.get(source, {})
        obs_fields = observed.get(source, {})
        for field, exp_type in exp_fields.items():
            if field in allow:
                continue
            if field not in obs_fields:
                rows.append(_row(source, field, exp_type, "", "missing_field", 0))
            elif obs_fields[field]["type"] != exp_type:
                rows.append(_row(source, field, exp_type, obs_fields[field]["type"], "type_change", obs_fields[field]["count"]))
        for field, info in obs_fields.items():
            if field not in exp_fields and field not in allow:
                rows.append(_row(source, field, "", info["type"], "new_field", info["count"]))
    rows.sort(key=lambda row: (row["source"].lower(), SEVERITY[row["drift_kind"]], row["field_path"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Source Schema Drift Report",
        "summary": {"drift_count": len(rows), "source_count": len({row["source"] for row in rows}), "missing_field_count": sum(1 for r in rows if r["drift_kind"] == "missing_field"), "type_change_count": sum(1 for r in rows if r["drift_kind"] == "type_change"), "new_field_count": sum(1 for r in rows if r["drift_kind"] == "new_field")},
        "drift_rows": rows,
    }


def render_source_schema_drift_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_source_schema_drift_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Source Schema Drift Report'}", "", "## Schema Drift", ""]
    lines.extend([f"- {r['source']} {r['field_path']}: {r['drift_kind']} ({r['expected_type']} -> {r['observed_type']})" for r in report.get("drift_rows") or []] or ["- No schema drift detected."])
    return "\n".join(lines).rstrip() + "\n"


def _observed(records: Iterable[dict[str, Any]] | dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    source = records.get("records") if isinstance(records, dict) else records
    observed: dict[str, dict[str, dict[str, Any]]] = {}
    for raw in source or []:
        if not isinstance(raw, dict):
            continue
        src = _text(raw.get("source")) or "unknown-source"
        field = _text(raw.get("field_path") or raw.get("field")) or "unknown_field"
        typ = _text(raw.get("observed_type") or raw.get("type")) or _infer(raw.get("value"))
        count = _int(raw.get("sample_count", raw.get("count", 1)))
        slot = observed.setdefault(src, {}).setdefault(field, {"type": typ, "count": 0})
        slot["count"] += count
    return observed


def _baseline(records: Iterable[dict[str, Any]] | dict[str, Any]) -> dict[str, dict[str, str]]:
    if not isinstance(records, dict):
        return {}
    return {str(src): {str(k): str(v) for k, v in fields.items()} for src, fields in (records.get("baseline") or {}).items()}


def _row(source: str, field: str, expected: str, observed: str, kind: str, count: int) -> dict[str, Any]:
    return {"source": source, "field_path": field, "expected_type": expected, "observed_type": observed, "drift_kind": kind, "sample_count": count, "recommended_adapter_action": _action(kind, field)}


def _action(kind: str, field: str) -> str:
    if kind == "missing_field":
        return f"restore extraction for {field}"
    if kind == "type_change":
        return f"update parser type handling for {field}"
    return f"review and map new field {field}"


def _infer(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string" if value is not None else "unknown"


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
