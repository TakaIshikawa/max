"""JSON API renderer for signal annotation coverage status."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.signal_annotation_coverage_status.v1"
KIND = "max.api.signal_annotation_coverage_status"


def signal_annotation_coverage_status_to_json(payload: Mapping[str, Any]) -> str:
    valid_roles = {str(role) for role in (payload.get("valid_roles") or ["owner", "reviewer", "approver", "observer"])}
    rows = [_signal(row, index, valid_roles) for index, row in enumerate(list_of_maps(payload.get("signals") or payload.get("rows")), start=1)]
    total = len(rows)
    annotated = sum(1 for row in rows if row["annotated"])
    invalid = sum(row["invalid_role_count"] for row in rows)
    coverage = round(annotated / total, 4) if total else 1.0
    warning = _float(payload.get("warning_min_coverage"), 0.9)
    critical = _float(payload.get("critical_min_coverage"), 0.5)
    status = "critical" if coverage < critical else ("warning" if coverage < warning or invalid else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "total_signals": total, "annotated_signals": annotated, "unannotated_signals": total - annotated, "invalid_role_count": invalid, "coverage": coverage}, "sources": _by_source(rows), "signals": rows, "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _signal(item: Mapping[str, Any], index: int, valid_roles: set[str]) -> dict[str, Any]:
    annotations = list_of_maps(item.get("annotations")) if isinstance(item.get("annotations"), list) else []
    role = item.get("annotation_role") or item.get("role")
    if role:
        annotations.append({"role": role})
    invalid = sum(1 for row in annotations if str(row.get("role") or "") not in valid_roles)
    annotated = bool(annotations) and invalid < len(annotations)
    return {"signal_id": _text(item.get("signal_id") or item.get("id") or f"signal-{index}"), "source": _text(item.get("source") or "unknown"), "annotated": annotated, "annotation_count": len(annotations), "invalid_role_count": invalid}


def _by_source(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["source"]].append(row)
    output = []
    for source, items in grouped.items():
        annotated = sum(1 for item in items if item["annotated"])
        output.append({"source": source, "total_signals": len(items), "annotated_signals": annotated, "unannotated_signals": len(items) - annotated, "invalid_role_count": sum(item["invalid_role_count"] for item in items), "coverage": round(annotated / len(items), 4) if items else 1.0})
    return sorted(output, key=lambda row: (row["coverage"], row["source"]))


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
