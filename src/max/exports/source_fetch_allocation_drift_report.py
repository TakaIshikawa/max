"""Source fetch allocation drift export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping

SCHEMA_VERSION = "max.source_fetch_allocation_drift_report.v1"
KIND = "max.source_fetch_allocation_drift_report"


def generate_source_fetch_allocation_drift_report(snapshots: list[Mapping[str, Any]], *, drift_threshold: float = 0.1, sustained_runs: int = 2) -> dict[str, Any]:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, Mapping):
            continue
        for record in _records(snapshot):
            source = _text(record.get("source")) or "unknown-source"
            planned = max(0, _float(record.get("planned_share") or record.get("planned_allocation") or record.get("planned")))
            actual = max(0, _float(record.get("actual_share") or record.get("actual_allocation") or record.get("actual")))
            suppressed = _truthy(record.get("suppressed") or record.get("circuit_breaker_open"))
            by_source[source].append({"run_index": index, "planned_share": planned, "actual_share": actual, "drift": round(actual - planned, 6), "suppressed": suppressed})
    rows = []
    for source, runs in by_source.items():
        latest = runs[-1]
        under = _streak(runs, drift_threshold, -1)
        over = _streak(runs, drift_threshold, 1)
        sustained = not latest["suppressed"] and (under >= sustained_runs or over >= sustained_runs)
        rows.append(
            {
                "source": source,
                "planned_share": latest["planned_share"],
                "actual_share": latest["actual_share"],
                "drift": latest["drift"],
                "underfetch_streak": under,
                "overfetch_streak": over,
                "suppressed": latest["suppressed"],
                "allocation_efficiency": round(latest["actual_share"] / latest["planned_share"], 4) if latest["planned_share"] else 0.0,
                "sustained_drift": sustained,
                "recommendation": _recommendation(latest["suppressed"], under, over, sustained_runs),
            }
        )
    rows.sort(key=lambda row: (0 if row["sustained_drift"] else 1, 0 if row["suppressed"] else 1, -abs(row["drift"]), row["source"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "source_count": len(rows),
            "sustained_drift_count": sum(1 for row in rows if row["sustained_drift"]),
            "suppressed_source_count": sum(1 for row in rows if row["suppressed"]),
        },
        "source_rows": rows,
        "rebalance_recommendations": [row for row in rows if row["sustained_drift"] or row["suppressed"]],
    }


def _records(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = snapshot.get("sources") or snapshot.get("records") or snapshot.get("allocations") or []
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _streak(runs: list[dict[str, Any]], threshold: float, direction: int) -> int:
    count = 0
    for run in reversed(runs):
        if run["suppressed"]:
            break
        drift = run["drift"]
        if (direction < 0 and drift <= -threshold) or (direction > 0 and drift >= threshold):
            count += 1
        else:
            break
    return count


def _recommendation(suppressed: bool, under: int, over: int, sustained_runs: int) -> str:
    if suppressed:
        return "resolve suppression before judging allocation fairness"
    if under >= sustained_runs:
        return "increase fetch allocation or inspect throttling"
    if over >= sustained_runs:
        return "reduce fetch allocation and rebalance capacity"
    return "no rebalance required"


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _truthy(value: Any) -> bool:
    return bool(value) and str(value).lower() not in {"false", "0", "none"}


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
