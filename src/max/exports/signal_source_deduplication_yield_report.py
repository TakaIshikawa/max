"""Signal source deduplication yield export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.signal_source_deduplication_yield_report.v1"
KIND = "max.signal_source_deduplication_yield_report"


def generate_signal_source_deduplication_yield_report(records: Iterable[dict[str, Any]], *, low_yield_threshold: float = 0.5) -> dict[str, Any]:
    threshold = _float(low_yield_threshold)
    rows = [_row(raw, threshold) for raw in records if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["source"].casefold()))
    low_yield_sources = [row for row in rows if row["low_yield"]]
    low_yield_sources.sort(key=lambda row: (row["yield_ratio"], row["source"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "source_count": len(rows),
            "low_yield_source_count": len(low_yield_sources),
            "raw_signal_count": sum(row["raw_signal_count"] for row in rows),
            "unique_signal_count": sum(row["unique_signal_count"] for row in rows),
            "low_yield_threshold": threshold,
        },
        "sources": rows,
        "low_yield_sources": low_yield_sources,
    }


def _row(raw: dict[str, Any], threshold: float) -> dict[str, Any]:
    raw_count = _int(raw.get("raw_signal_count") or raw.get("raw_count") or raw.get("total_signal_count"))
    unique_count = min(raw_count, _int(raw.get("unique_signal_count") or raw.get("unique_count") or raw.get("deduplicated_signal_count")))
    duplicate_count = max(0, raw_count - unique_count)
    yield_ratio = _rate(unique_count, raw_count)
    return {
        "source": _text(raw.get("source") or raw.get("source_name") or raw.get("adapter")) or "unknown-source",
        "raw_signal_count": raw_count,
        "unique_signal_count": unique_count,
        "duplicate_signal_count": duplicate_count,
        "yield_ratio": yield_ratio,
        "duplicate_ratio": _rate(duplicate_count, raw_count),
        "low_yield": raw_count > 0 and yield_ratio < threshold,
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
