"""Publication destination cost spike export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.publication_destination_cost_spike_report.v1"
KIND = "max.publication_destination_cost_spike_report"
SEVERITY_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def generate_publication_destination_cost_spike_report(
    records: Iterable[dict[str, Any]],
    *,
    warning_ratio: float = 1.25,
    critical_ratio: float = 2.0,
) -> dict[str, Any]:
    rows = [_row(raw, index, warning_ratio, critical_ratio) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["severity_rank"], -row["cost_delta"], row["destination"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "destination_count": len(rows),
            "spiking_destination_count": sum(1 for row in rows if row["status"] != "healthy"),
            "critical_count": sum(1 for row in rows if row["status"] == "critical"),
            "excess_cost_usd": round(sum(max(0.0, row["cost_delta"]) for row in rows if row["status"] != "healthy"), 2),
        },
        "destination_rows": rows,
    }


def _row(raw: dict[str, Any], index: int, warning_ratio: float, critical_ratio: float) -> dict[str, Any]:
    current = _money(raw.get("current_cost_usd") or raw.get("current_cost") or raw.get("actual_cost_usd"))
    baseline = _money(raw.get("baseline_cost_usd") or raw.get("baseline_cost") or raw.get("expected_cost_usd"))
    delta = round(current - baseline, 2)
    ratio = _ratio(current, baseline)
    status = _status(current, baseline, ratio, warning_ratio, critical_ratio)
    return {
        "destination": _text(raw.get("destination") or raw.get("destination_id") or raw.get("channel")) or f"destination-{index}",
        "current_cost_usd": round(current, 2),
        "baseline_cost_usd": round(baseline, 2),
        "cost_delta": delta,
        "cost_ratio": ratio,
        "window_hours": _int(raw.get("window_hours")),
        "publication_count": _int(raw.get("publication_count") or raw.get("publications")),
        "status": status,
        "reason": _reason(current, baseline, status),
        "severity_rank": SEVERITY_RANK[status],
    }


def _status(current: float, baseline: float, ratio: float | None, warning_ratio: float, critical_ratio: float) -> str:
    if current <= baseline:
        return "healthy"
    if baseline == 0:
        return "critical" if current > 0 else "healthy"
    if ratio is not None and ratio >= critical_ratio:
        return "critical"
    if ratio is not None and ratio >= warning_ratio:
        return "warning"
    return "healthy"


def _reason(current: float, baseline: float, status: str) -> str:
    if status == "healthy":
        return "within_baseline"
    if baseline == 0:
        return "zero_baseline_spend"
    return "cost_spike"


def _ratio(current: float, baseline: float) -> float | None:
    if baseline == 0:
        return None if current > 0 else 1.0
    return round(current / baseline, 4)


def _money(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
