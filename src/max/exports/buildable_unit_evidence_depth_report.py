"""Buildable unit evidence depth export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.buildable_unit_evidence_depth_report.v1"
KIND = "max.buildable_unit_evidence_depth_report"

_STATUS_ORDER = {"blocked": 0, "thin": 1, "ready": 2}


def generate_buildable_unit_evidence_depth_report(
    units: Iterable[dict[str, Any]], *, min_signal_count: int = 3, min_insight_count: int = 1
) -> dict[str, Any]:
    rows = []
    signal_threshold = _int(min_signal_count)
    insight_threshold = _int(min_insight_count)
    for index, raw in enumerate(units):
        if not isinstance(raw, dict):
            continue
        signals = _first_present(raw, "signals", "evidence_signals", "signal_evidence")
        insights = _first_present(raw, "insights", "evidence_insights", "synthesis_insights")
        sources = _first_present(raw, "sources", "evidence_sources", "source_refs")
        missing = [
            field
            for field, value in (("signals", signals), ("insights", insights), ("sources", sources))
            if value is None
        ]
        signal_count = _count(raw.get("signal_count"), signals)
        insight_count = _count(raw.get("insight_count"), insights)
        source_count = _count(raw.get("source_count"), sources)
        status = _status(missing, signal_count, insight_count, signal_threshold, insight_threshold)
        rows.append(
            {
                "unit_id": _text(raw.get("unit_id") or raw.get("buildable_unit_id") or raw.get("id")) or f"unit-{index + 1}",
                "signal_count": signal_count,
                "insight_count": insight_count,
                "source_count": source_count,
                "missing_evidence_fields": missing,
                "status": status,
            }
        )

    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["unit_id"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "unit_count": len(rows),
            "ready_count": sum(1 for row in rows if row["status"] == "ready"),
            "thin_count": sum(1 for row in rows if row["status"] == "thin"),
            "blocked_count": sum(1 for row in rows if row["status"] == "blocked"),
            "min_signal_count": signal_threshold,
            "min_insight_count": insight_threshold,
        },
        "rows": rows,
    }


def _status(missing: list[str], signal_count: int, insight_count: int, min_signal_count: int, min_insight_count: int) -> str:
    if missing:
        return "blocked"
    if signal_count >= min_signal_count and insight_count >= min_insight_count:
        return "ready"
    return "thin"


def _first_present(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _count(explicit: Any, collection: Any) -> int:
    value = _int(explicit)
    if value:
        return value
    if collection is None or collection == "":
        return 0
    if isinstance(collection, (list, tuple, set, dict)):
        return len(collection)
    return 1


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
