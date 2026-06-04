"""JSON API renderer for spec evidence trace completeness status."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import as_list, list_of_maps, source_metadata, strings

SCHEMA_VERSION = "max.api.spec_evidence_trace_completeness_status.v1"
KIND = "max.api.spec_evidence_trace_completeness_status"
STATUS_RANK = {"critical": 0, "warning": 1, "ok": 2}


def spec_evidence_trace_completeness_status_to_json(payload: Mapping[str, Any]) -> str:
    rows = [_row(item, index) for index, item in enumerate(_items(payload), start=1)]
    rows.sort(key=lambda row: (STATUS_RANK[row["status"]], row["completeness_ratio"], row["spec_id"]))
    return json.dumps({"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"spec_count": len(rows), "blocking_spec_count": sum(1 for row in rows if row["status"] == "critical"), "unit_completeness_ratio": _ratio(rows, "unit_reference_count"), "insight_completeness_ratio": _ratio(rows, "insight_reference_count"), "signal_completeness_ratio": _ratio(rows, "signal_reference_count"), "status": "critical" if any(row["status"] == "critical" for row in rows) else "warning" if any(row["status"] == "warning" for row in rows) else "insufficient_data" if not rows else "ok"}, "spec_rows": rows, "metadata": source_metadata(payload, spec_count=len(rows))}, indent=2, sort_keys=True)


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list_of_maps(payload.get("specs") or payload.get("rows") or payload.get("items"))


def _row(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    units = strings(item.get("unit_ids") or item.get("buildable_unit_ids") or item.get("unit_id"))
    insights = strings(item.get("insight_ids") or item.get("insights") or item.get("insight_id"))
    signals = strings(item.get("signal_ids") or item.get("signals") or item.get("signal_id"))
    evidence = [str(value) for value in as_list(item.get("evidence_ids") or item.get("evidence_id")) if value not in (None, "")]
    issues = []
    if not units:
        issues.append("missing_unit_reference")
    if not insights:
        issues.append("missing_insight_reference")
    if not signals:
        issues.append("missing_signal_reference")
    duplicates = sorted({value for value in evidence if evidence.count(value) > 1})
    issues.extend(f"duplicate_evidence:{value}" for value in duplicates)
    present = sum(1 for values in (units, insights, signals) if values)
    status = "critical" if not units or not insights else "warning" if issues else "ok"
    return {"spec_id": _text(item.get("spec_id") or item.get("id")) or f"spec-{index}", "unit_reference_count": len(units), "insight_reference_count": len(insights), "signal_reference_count": len(signals), "completeness_ratio": round(present / 3, 4), "issues": issues, "status": status}


def _ratio(rows: list[dict[str, Any]], key: str) -> float:
    return round(sum(1 for row in rows if row[key] > 0) / len(rows), 4) if rows else 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
