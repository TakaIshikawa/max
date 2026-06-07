"""Feedback loop weight impact export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.feedback_loop_weight_impact_report.v1"
KIND = "max.feedback_loop_weight_impact_report"


def generate_feedback_loop_weight_impact_report(records: Iterable[dict[str, Any]], *, material_delta_threshold: float = 0.2) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        profile = _text(raw.get("profile")) or "unknown-profile"
        dimension = _text(raw.get("dimension")) or "unknown-dimension"
        row = groups.setdefault(
            (profile, dimension),
            {
                "profile": profile,
                "dimension": dimension,
                "approval_count": 0,
                "rejection_count": 0,
                "starting_weight": None,
                "ending_weight": None,
            },
        )
        row["approval_count"] += _int(raw.get("approval_count") or raw.get("approvals"))
        row["rejection_count"] += _int(raw.get("rejection_count") or raw.get("rejections"))
        if _text(raw.get("outcome")).lower() in {"approve", "approved", "accepted"}:
            row["approval_count"] += 1
        if _text(raw.get("outcome")).lower() in {"reject", "rejected", "declined"}:
            row["rejection_count"] += 1
        start = raw.get("starting_weight", raw.get("previous_weight"))
        end = raw.get("ending_weight", raw.get("current_weight"))
        if start is not None and row["starting_weight"] is None:
            row["starting_weight"] = _float(start)
        if end is not None:
            row["ending_weight"] = _float(end)
        if raw.get("weight_delta") is not None and row["ending_weight"] is None:
            row["ending_weight"] = _float(row["starting_weight"]) + _float(raw.get("weight_delta"))

    rows = []
    for row in groups.values():
        starting = _float(row["starting_weight"])
        ending = _float(row["ending_weight"] if row["ending_weight"] is not None else starting)
        delta = round(ending - starting, 4)
        rows.append(
            {
                "profile": row["profile"],
                "dimension": row["dimension"],
                "approval_count": row["approval_count"],
                "rejection_count": row["rejection_count"],
                "starting_weight": starting,
                "ending_weight": ending,
                "weight_delta": delta,
                "status": "material" if abs(delta) >= material_delta_threshold else "stable",
            }
        )
    rows.sort(key=lambda row: (-abs(row["weight_delta"]), row["profile"].lower(), row["dimension"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "material_count": sum(1 for row in rows if row["status"] == "material"), "material_delta_threshold": material_delta_threshold}, "rows": rows}


def _float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
