"""Adapter payload shape drift export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_adapter_payload_shape_drift_report(payload_samples: Iterable[dict[str, Any]], expected_fields_by_source: Mapping[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in payload_samples:
        groups[_text(sample.get("source")) or "unknown"].append(sample)
    for source in expected_fields_by_source:
        groups.setdefault(_text(source) or "unknown", [])
    rows = []
    for source, samples in groups.items():
        expected = _fields(expected_fields_by_source.get(source))
        observed: set[str] = set()
        missing_counts = {field: 0 for field in expected}
        for sample in samples:
            payload = sample.get("payload") if isinstance(sample.get("payload"), Mapping) else sample
            keys = {str(key) for key in payload.keys() if key != "source"}
            observed.update(keys)
            for field in expected:
                if field not in keys:
                    missing_counts[field] += 1
        missing = sorted(field for field, count in missing_counts.items() if count > 0)
        unexpected = sorted(observed - expected) if expected else sorted(observed)
        severity = "critical" if any(missing_counts[field] == len(samples) and samples for field in missing) else ("warn" if missing or unexpected or not samples or not expected else "ok")
        rows.append({"source": source, "sample_count": len(samples), "expected_fields": sorted(expected), "observed_fields": sorted(observed), "missing_fields": missing, "unexpected_fields": unexpected, "severity": severity, "recommendation": "Block adapter release until required fields are restored." if severity == "critical" else ("Review payload contract drift." if severity == "warn" else "No action required.")})
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["source"]))
    return {"schema_version": "max.adapter_payload_shape_drift_report.v1", "kind": "max.adapter_payload_shape_drift_report", "summary": {"source_count": len(rows), "drifted_source_count": sum(1 for row in rows if row["severity"] != "ok")}, "rows": rows}


def _fields(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        value = value.get("required") or value.get("fields") or value.keys()
    if isinstance(value, (list, tuple, set)):
        return {_text(item) for item in value if _text(item)}
    return set()


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
