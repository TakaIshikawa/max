"""Synthesis throughput export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.synthesis_throughput_report.v1"
KIND = "max.synthesis_throughput_report"

_STATUS_ORDER = {"failing": 0, "low_yield": 1, "ok": 2}


def generate_synthesis_throughput_report(
    batches: Iterable[dict[str, Any]], *, min_insights_per_batch: int = 1
) -> dict[str, Any]:
    minimum = _int(min_insights_per_batch)
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"batch_count": 0, "signal_count": 0, "insight_count": 0, "failed_batch_count": 0}
    )
    for raw in batches:
        if not isinstance(raw, dict):
            continue
        key = (
            _text(raw.get("profile") or raw.get("profile_id") or raw.get("domain_profile")) or "default",
            _text(raw.get("model") or raw.get("model_id") or raw.get("provider_model")) or "unknown-model",
        )
        groups[key]["batch_count"] += 1
        groups[key]["signal_count"] += _int(raw.get("signal_count") or raw.get("signals_processed") or raw.get("input_signal_count"))
        groups[key]["insight_count"] += _int(raw.get("insight_count") or raw.get("insights_generated") or raw.get("output_insight_count"))
        if _failed(raw):
            groups[key]["failed_batch_count"] += 1

    rows = []
    for (profile, model), totals in groups.items():
        avg_insights = _rate(totals["insight_count"], totals["batch_count"])
        rows.append(
            {
                "profile": profile,
                "model": model,
                "batch_count": totals["batch_count"],
                "signal_count": totals["signal_count"],
                "insight_count": totals["insight_count"],
                "failed_batch_count": totals["failed_batch_count"],
                "avg_insights_per_batch": avg_insights,
                "conversion_rate": _rate(totals["insight_count"], totals["signal_count"]),
                "status": _status(totals["batch_count"], totals["failed_batch_count"], avg_insights, minimum),
            }
        )

    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["profile"].casefold(), row["model"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "group_count": len(rows),
            "batch_count": sum(row["batch_count"] for row in rows),
            "failed_batch_count": sum(row["failed_batch_count"] for row in rows),
            "signal_count": sum(row["signal_count"] for row in rows),
            "insight_count": sum(row["insight_count"] for row in rows),
            "min_insights_per_batch": minimum,
            "status": rows[0]["status"] if rows else "ok",
        },
        "rows": rows,
    }


def _status(batch_count: int, failed_count: int, avg_insights: float, minimum: int) -> str:
    if failed_count and failed_count == batch_count:
        return "failing"
    if failed_count or avg_insights < minimum:
        return "low_yield"
    return "ok"


def _failed(raw: dict[str, Any]) -> bool:
    status = _text(raw.get("status") or raw.get("state") or raw.get("outcome")).lower()
    return status in {"failed", "failure", "error", "timeout"}


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
