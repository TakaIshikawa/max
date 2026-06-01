"""JSON API renderer for insight evidence chain gap status."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from max.api._renderer_utils import list_of_maps, source_metadata

SCHEMA_VERSION = "max.api.insight_evidence_chain_gap_status.v1"
KIND = "max.api.insight_evidence_chain_gap_status"


def insight_evidence_chain_gap_status_to_json(payload: Mapping[str, Any]) -> str:
    known = {str(item) for item in (payload.get("known_signal_ids") or payload.get("signal_ids") or [])}
    min_evidence = _int(payload.get("minimum_evidence_count"), 2)
    rows = [_insight(row, index, known, min_evidence) for index, row in enumerate(list_of_maps(payload.get("insights") or payload.get("rows")), start=1)]
    rows.sort(key=lambda row: (-row["risk_score"], row["insight_id"]))
    total = len(rows)
    missing_ref = sum(1 for row in rows if row["missing_signal_reference_count"])
    missing_rate = round(missing_ref / total, 4) if total else 0.0
    critical = _float(payload.get("critical_missing_reference_rate"), 0.2)
    warning = _float(payload.get("warning_gap_rate"), 0.01)
    gap_count = sum(1 for row in rows if row["risk_score"])
    gap_rate = (gap_count / total) if total else 0.0
    status = "critical" if missing_rate >= critical and missing_ref else ("warning" if gap_rate >= warning and gap_count else "healthy")
    normalized = {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"status": status, "insight_count": total, "no_evidence_count": sum(1 for row in rows if row["no_evidence"]), "missing_signal_reference_count": missing_ref, "weak_evidence_count": sum(1 for row in rows if row["weak_evidence"]), "missing_reference_rate": missing_rate}, "insights": rows, "per_profile": _profiles(rows), "top_impacted_insights": rows[: _int(payload.get("max_impacted_insights"), 5)], "metadata": source_metadata(payload)}
    return json.dumps(normalized, indent=2, sort_keys=True)


def _insight(item: Mapping[str, Any], index: int, known: set[str], minimum: int) -> dict[str, Any]:
    evidence = list_of_maps(item.get("evidence") or item.get("evidence_items"))
    refs = [str(ref) for row in evidence for ref in (row.get("signal_refs") or row.get("signal_ids") or ([row.get("signal_id")] if row.get("signal_id") else []))]
    missing = [ref for ref in refs if known and ref not in known]
    no_evidence = not evidence
    weak = bool(evidence) and len(evidence) < minimum
    risk = (3 if no_evidence else 0) + len(missing) * 2 + (1 if weak else 0)
    return {"insight_id": _text(item.get("insight_id") or item.get("id") or f"insight-{index}"), "profile": _text(item.get("profile") or "default"), "evidence_count": len(evidence), "no_evidence": no_evidence, "missing_signal_reference_count": len(missing), "missing_signal_refs": sorted(missing), "weak_evidence": weak, "risk_score": risk}


def _profiles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["profile"]].append(row)
    output = [{"profile": profile, "insight_count": len(items), "gap_count": sum(1 for item in items if item["risk_score"]), "missing_signal_reference_count": sum(1 for item in items if item["missing_signal_reference_count"]), "weak_evidence_count": sum(1 for item in items if item["weak_evidence"])} for profile, items in grouped.items()]
    return sorted(output, key=lambda row: (-row["gap_count"], row["profile"]))


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
