"""Source adapter latency regression export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.source_adapter_latency_regression_report.v1"
KIND = "max.source_adapter_latency_regression_report"


def generate_source_adapter_latency_regression_report(
    records: Iterable[dict[str, Any]],
    *,
    baseline_p95_ms: float = 1000,
    regression_ratio: float = 1.25,
) -> dict[str, Any]:
    baseline_floor = _float(baseline_p95_ms)
    ratio_threshold = _float(regression_ratio)
    rows = []
    adapter_count = 0
    missing_sample_count = 0

    for raw in records:
        if not isinstance(raw, dict):
            missing_sample_count += 1
            continue
        adapter = _text(raw.get("adapter") or raw.get("source_adapter") or raw.get("source") or raw.get("name"))
        current = _float(raw.get("current_p95_ms") or raw.get("p95_ms") or raw.get("latency_p95_ms"))
        baseline = _float(raw.get("baseline_p95_ms") or raw.get("previous_p95_ms") or raw.get("prior_p95_ms") or baseline_floor)
        sample_count = _int(raw.get("sample_count") or raw.get("samples") or raw.get("request_count") or raw.get("run_count"))
        baseline_sample_count = _int(raw.get("baseline_sample_count") or raw.get("previous_sample_count") or raw.get("prior_sample_count") or sample_count)

        if not adapter or current <= 0 or baseline <= 0 or sample_count <= 0 or baseline_sample_count <= 0:
            missing_sample_count += 1
            continue

        adapter_count += 1
        observed_ratio = round(current / baseline, 4)
        if current <= baseline_floor or observed_ratio < ratio_threshold:
            continue

        rows.append(
            {
                "adapter": adapter,
                "current_p95_ms": round(current, 2),
                "baseline_p95_ms": round(baseline, 2),
                "regression_ratio": observed_ratio,
                "sample_count": sample_count,
                "baseline_sample_count": baseline_sample_count,
            }
        )

    rows.sort(key=lambda row: (-row["regression_ratio"], row["adapter"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "adapter_count": adapter_count,
            "regressed_adapter_count": len(rows),
            "missing_sample_count": missing_sample_count,
            "baseline_p95_ms": round(baseline_floor, 2),
            "regression_ratio_threshold": ratio_threshold,
            "worst_regression_ratio": rows[0]["regression_ratio"] if rows else 0.0,
        },
        "rows": rows,
    }


def _float(value: Any) -> float:
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
