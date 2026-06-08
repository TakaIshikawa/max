"""Insight evidence chain gap export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.insight_evidence_chain_gap_report.v1"
KIND = "max.insight_evidence_chain_gap_report"


def generate_insight_evidence_chain_gap_report(records: Iterable[dict[str, Any]], *, completeness_threshold: float = 1.0) -> dict[str, Any]:
    threshold = _ratio(completeness_threshold)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, dict):
            continue
        profile = _text(raw.get("profile") or raw.get("domain_profile")) or "default"
        insight_id = _text(raw.get("insight_id") or raw.get("id")) or "unknown-insight"
        expected = _link_set(raw.get("expected_links") or raw.get("expected_signal_ids") or raw.get("expected"))
        present = _link_set(raw.get("present_links") or raw.get("present_signal_ids") or raw.get("links") or raw.get("evidence"))
        group = groups.setdefault((profile, insight_id), {"expected": set(), "present": set(), "missing": set()})
        group["expected"].update(expected)
        group["present"].update(present)
        group["missing"].update(_link_set(raw.get("missing_links") or raw.get("missing_signal_ids") or raw.get("missing_link_types")))
    rows = []
    for (profile, insight_id), group in groups.items():
        missing = (group["expected"] - group["present"]) | group["missing"]
        expected_count = len(group["expected"]) or len(group["present"]) + len(missing)
        present_count = len(group["present"] - missing)
        completeness_rate = round(present_count / expected_count, 4) if expected_count else 1.0
        rows.append({"profile": profile, "insight_id": insight_id, "expected_links": expected_count, "present_links": present_count, "missing_links": sorted(missing, key=str.lower), "completeness_rate": completeness_rate, "status": "gapped" if completeness_rate < threshold else "complete"})
    rows.sort(key=lambda row: (row["profile"].lower(), row["insight_id"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "gapped_count": sum(1 for row in rows if row["status"] == "gapped"), "completeness_threshold": threshold}, "rows": rows}


def _link_set(value: Any) -> set[str]:
    if isinstance(value, dict):
        items = value.keys()
    elif isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, list | tuple | set):
        items = value
    else:
        items = []
    return {_text(item) for item in items if _text(item)}


def _ratio(value: Any) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 1.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
