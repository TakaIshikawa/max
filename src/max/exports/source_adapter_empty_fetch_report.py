"""Source adapter empty fetch export report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_empty_fetch_report.v1"
KIND = "max.source_adapter_empty_fetch_report"


def generate_source_adapter_empty_fetch_report(fetch_runs: Iterable[dict[str, Any]], *, empty_rate_threshold: float = 0.3) -> dict[str, Any]:
    threshold = _float(empty_rate_threshold)
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"attempt_count": 0, "empty_attempt_count": 0, "fetched_count": 0})
    for raw in fetch_runs:
        if not isinstance(raw, dict):
            continue
        key = (
            _text(raw.get("adapter") or raw.get("source_adapter") or raw.get("source")) or "unknown-adapter",
            _text(raw.get("profile") or raw.get("profile_id") or raw.get("profile_name")) or "default",
        )
        fetched = _int(raw.get("fetched_count") or raw.get("item_count") or raw.get("signal_count") or raw.get("count"))
        grouped[key]["attempt_count"] += 1
        grouped[key]["fetched_count"] += fetched
        if fetched == 0:
            grouped[key]["empty_attempt_count"] += 1

    rows = []
    for (adapter, profile), totals in grouped.items():
        empty_rate = _rate(totals["empty_attempt_count"], totals["attempt_count"])
        rows.append(
            {
                "adapter": adapter,
                "profile": profile,
                "attempt_count": totals["attempt_count"],
                "empty_attempt_count": totals["empty_attempt_count"],
                "fetched_count": totals["fetched_count"],
                "empty_rate": empty_rate,
                "flagged": empty_rate >= threshold,
            }
        )
    rows.sort(key=lambda row: (-row["empty_rate"], row["adapter"].casefold(), row["profile"].casefold()))
    flagged = [row for row in rows if row["flagged"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "pair_count": len(rows),
            "flagged_pair_count": len(flagged),
            "attempt_count": sum(row["attempt_count"] for row in rows),
            "empty_attempt_count": sum(row["empty_attempt_count"] for row in rows),
            "empty_rate_threshold": threshold,
        },
        "rows": rows,
        "flagged_pairs": flagged,
    }


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
