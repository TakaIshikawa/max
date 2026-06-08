"""Domain profile schema drift export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.domain_profile_schema_drift_report.v1"
KIND = "max.domain_profile_schema_drift_report"


def generate_domain_profile_schema_drift_report(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        profile = _text(raw.get("profile") or raw.get("domain_profile")) or "default"
        version = _text(raw.get("schema_version") or raw.get("version")) or "unknown"
        group = groups.setdefault((profile, version), {"missing": 0, "unknown": 0, "type": 0, "deprecated": 0, "fields": set()})
        findings = _items(raw.get("findings") or raw.get("issues") or raw.get("validation_findings")) or [raw]
        for finding in findings:
            issue = _issue_type(finding)
            field = _field(finding)
            if issue == "missing_field":
                group["missing"] += 1
            elif issue == "unknown_field":
                group["unknown"] += 1
            elif issue == "type_mismatch":
                group["type"] += 1
            elif issue == "deprecated_field":
                group["deprecated"] += 1
            if field:
                group["fields"].add(field)
    rows = []
    for (profile, version), group in groups.items():
        drifted = group["missing"] > 0 or group["type"] > 0
        rows.append({"profile": profile, "schema_version": version, "missing_fields": group["missing"], "unknown_fields": group["unknown"], "type_mismatches": group["type"], "deprecated_fields": group["deprecated"], "issue_fields": sorted(group["fields"], key=str.lower), "status": "drifted" if drifted else "compatible"})
    rows.sort(key=lambda row: (row["profile"].lower(), row["schema_version"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "drifted_count": sum(1 for row in rows if row["status"] == "drifted")}, "rows": rows}


def _items(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list | tuple | set):
        return list(value)
    return []


def _issue_type(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("issue_type") or value.get("type") or value.get("kind")
    text = _text(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {"missing": "missing_field", "unknown": "unknown_field", "extra_field": "unknown_field", "type": "type_mismatch", "deprecated": "deprecated_field"}
    return aliases.get(text, text)


def _field(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("field") or value.get("field_name") or value.get("path"))
    return ""


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
