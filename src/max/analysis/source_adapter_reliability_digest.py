"""Source adapter reliability digest from persisted run and utilization metrics."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from io import StringIO
from typing import TYPE_CHECKING, Any

from max.sources.base import snapshot_circuit_breakers
from max.sources.registry import get_adapter

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.source_adapter.reliability_digest.v1"
KIND = "max.source_adapter.reliability_digest"

_SUCCESS_STATUSES = {"ok", "success", "completed"}
_BAND_ORDER = {
    "failing": 0,
    "low_yield": 1,
    "watch": 2,
    "healthy": 3,
}
_CSV_COLUMNS = [
    "adapter_name",
    "source_type",
    "successes",
    "failures",
    "failure_rate",
    "circuit_breaker_state",
    "latest_error",
    "recommendation",
    "priority",
    "severity",
    "reliability_band",
    "reliability_score",
    "run_count",
    "success_rate",
    "average_fetched_signals",
    "average_duration_ms",
    "combined_hit_rate",
    "latest_status",
]
_CSV_PRIORITY_BY_BAND = {
    "failing": "p0",
    "low_yield": "p1",
    "watch": "p2",
    "healthy": "p3",
}
_CSV_SEVERITY_BY_BAND = {
    "failing": "critical",
    "low_yield": "high",
    "watch": "medium",
    "healthy": "low",
}


def build_source_adapter_reliability_digest(
    store: Store,
    limit: int = 20,
    min_runs: int = 1,
) -> dict[str, Any]:
    """Build a deterministic reliability digest for source adapters."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if min_runs < 1:
        raise ValueError("min_runs must be at least 1")

    runs = store.get_pipeline_runs(limit=limit)
    quality_stats = store.get_adapter_quality_stats()
    adapter_rollups = _adapter_rollups(runs)
    adapters = sorted(adapter_rollups)

    rows = [
        _adapter_report(adapter, adapter_rollups[adapter], quality_stats.get(adapter))
        for adapter in adapters
        if adapter_rollups[adapter]["run_count"] >= min_runs
    ]
    rows.sort(key=lambda row: (_BAND_ORDER[row["reliability_band"]], row["reliability_score"], row["adapter"]))

    bands = {
        band: [row["adapter"] for row in rows if row["reliability_band"] == band]
        for band in ("failing", "low_yield", "watch", "healthy")
    }
    next_actions = _report_next_actions(rows, runs=runs, quality_stats=quality_stats)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "limit": limit,
            "min_runs": min_runs,
        },
        "summary": {
            "run_count": len(runs),
            "adapter_count": len(rows),
            "excluded_below_min_runs_count": len(adapters) - len(rows),
            "healthy_count": len(bands["healthy"]),
            "watch_count": len(bands["watch"]),
            "low_yield_count": len(bands["low_yield"]),
            "failing_count": len(bands["failing"]),
            "latest_run_started_at": runs[0]["started_at"] if runs else None,
        },
        "reliability_bands": bands,
        "adapters": rows,
        "next_actions": next_actions,
    }


def render_source_adapter_reliability_digest(
    report: dict[str, Any],
    fmt: str = "json",
) -> str:
    """Render a source adapter reliability digest as deterministic JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported source adapter reliability digest format: {fmt}")

    summary = report["summary"]
    lines = [
        "# Source Adapter Reliability Digest",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Runs analyzed: {summary['run_count']}",
        f"Adapters ranked: {summary['adapter_count']}",
        "",
        "## Summary",
        "",
        f"- Failing: {summary['failing_count']}",
        f"- Low yield: {summary['low_yield_count']}",
        f"- Watch: {summary['watch_count']}",
        f"- Healthy: {summary['healthy_count']}",
        "",
        "## Adapter Rankings",
        "",
    ]

    if report["adapters"]:
        lines.append("| Adapter | Band | Score | Runs | Success | Failure | Avg fetched | Utilization |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in report["adapters"]:
            utilization = row["utilization"]
            lines.append(
                f"| `{row['adapter']}` | {row['reliability_band']} | "
                f"{row['reliability_score']:.3f} | {row['run_count']} | "
                f"{row['success_count']} | {row['failure_count']} | "
                f"{row['average_fetched_signals']:.2f} | "
                f"{utilization['combined_hit_rate']:.3f} |"
            )
    else:
        lines.append("No adapter run metrics are available for this report.")

    lines.extend(["", "## Follow-Up Actions", ""])
    lines.extend(f"- {action}" for action in report["next_actions"])
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    circuit_states = _csv_circuit_breaker_states()
    rows = sorted(
        report.get("adapters", []),
        key=lambda row: (
            _BAND_ORDER.get(str(row.get("reliability_band")), len(_BAND_ORDER)),
            _csv_float(row.get("reliability_score")),
            str(row.get("adapter") or ""),
        ),
    )
    for row in rows:
        writer.writerow(_csv_adapter_row(row, circuit_states))
    return output.getvalue()


def _csv_adapter_row(row: Mapping[str, Any], circuit_states: Mapping[str, str]) -> dict[str, Any]:
    adapter = str(row.get("adapter") or "")
    reliability_band = str(row.get("reliability_band") or "")
    run_count = _nonnegative_int(row.get("run_count"))
    failures = _nonnegative_int(row.get("failure_count"))
    failure_rate = round(failures / run_count, 3) if run_count else 0.0
    return {
        "adapter_name": adapter,
        "source_type": _csv_source_type(row, adapter),
        "successes": _nonnegative_int(row.get("success_count")),
        "failures": failures,
        "failure_rate": failure_rate,
        "circuit_breaker_state": _csv_circuit_breaker_state(row, adapter, circuit_states),
        "latest_error": row.get("last_error") or row.get("latest_error") or "",
        "recommendation": _csv_recommendation(row),
        "priority": row.get("priority") or _CSV_PRIORITY_BY_BAND.get(reliability_band, ""),
        "severity": row.get("severity") or _CSV_SEVERITY_BY_BAND.get(reliability_band, ""),
        "reliability_band": reliability_band,
        "reliability_score": row.get("reliability_score", ""),
        "run_count": run_count,
        "success_rate": row.get("success_rate", ""),
        "average_fetched_signals": row.get("average_fetched_signals", ""),
        "average_duration_ms": row.get("average_duration_ms", ""),
        "combined_hit_rate": _csv_combined_hit_rate(row),
        "latest_status": row.get("latest_status", ""),
    }


def _csv_circuit_breaker_states() -> dict[str, str]:
    return {
        snapshot.adapter_name: snapshot.state
        for snapshot in snapshot_circuit_breakers()
    }


def _csv_circuit_breaker_state(
    row: Mapping[str, Any],
    adapter: str,
    circuit_states: Mapping[str, str],
) -> str:
    direct = row.get("circuit_breaker_state")
    if direct:
        return str(direct)
    circuit_breaker = row.get("circuit_breaker")
    if isinstance(circuit_breaker, Mapping) and circuit_breaker.get("state"):
        return str(circuit_breaker["state"])
    return circuit_states.get(adapter, "")


def _csv_combined_hit_rate(row: Mapping[str, Any]) -> Any:
    utilization = row.get("utilization")
    if isinstance(utilization, Mapping):
        return utilization.get("combined_hit_rate", "")
    return row.get("combined_hit_rate", "")


def _csv_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _csv_recommendation(row: Mapping[str, Any]) -> str:
    recommendation = row.get("recommendation")
    if recommendation:
        return str(recommendation)
    recommendations = row.get("recommendations")
    if not isinstance(recommendations, list):
        return ""
    return " | ".join(str(item) for item in recommendations if item)


def _csv_source_type(row: Mapping[str, Any], adapter: str) -> str:
    source_type = row.get("source_type")
    if source_type:
        return str(source_type)
    if not adapter:
        return ""
    try:
        adapter_source_type = get_adapter(adapter).source_type
    except Exception:
        return "unknown"
    if hasattr(adapter_source_type, "value"):
        return str(adapter_source_type.value)
    return str(adapter_source_type)


def _adapter_rollups(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rollups: dict[str, dict[str, Any]] = {}
    for run in runs:
        adapter_metrics = run.get("adapter_metrics") or {}
        if not isinstance(adapter_metrics, Mapping):
            continue
        for adapter, raw_metrics in adapter_metrics.items():
            if not isinstance(raw_metrics, Mapping):
                continue
            name = str(adapter)
            item = rollups.setdefault(
                name,
                {
                    "run_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "signal_count_total": 0,
                    "duration_ms_total": 0,
                    "duration_ms_count": 0,
                    "last_error": "",
                    "latest_status": "unknown",
                },
            )
            status = str(raw_metrics.get("status") or "unknown")
            signal_count = _nonnegative_int(raw_metrics.get("signal_count"))
            duration_ms = raw_metrics.get("duration_ms")

            item["run_count"] += 1
            item["signal_count_total"] += signal_count
            if isinstance(duration_ms, int | float) and duration_ms >= 0:
                item["duration_ms_total"] += float(duration_ms)
                item["duration_ms_count"] += 1
            if status in _SUCCESS_STATUSES:
                item["success_count"] += 1
            else:
                item["failure_count"] += 1
                error = raw_metrics.get("error_message")
                if not item["last_error"] and error:
                    item["last_error"] = str(error)
            if item["run_count"] == 1:
                item["latest_status"] = status
    return rollups


def _adapter_report(
    adapter: str,
    rollup: dict[str, Any],
    quality: Mapping[str, Any] | None,
) -> dict[str, Any]:
    run_count = int(rollup["run_count"])
    success_count = int(rollup["success_count"])
    failure_count = int(rollup["failure_count"])
    average_fetched = round(float(rollup["signal_count_total"]) / run_count, 3)
    success_rate = round(success_count / run_count, 3)
    average_duration_ms = None
    if rollup["duration_ms_count"]:
        average_duration_ms = round(rollup["duration_ms_total"] / rollup["duration_ms_count"], 1)

    utilization = _utilization_stats(quality)
    score = _reliability_score(
        success_rate=success_rate,
        average_fetched=average_fetched,
        utilization_rate=utilization["combined_hit_rate"],
    )
    band = _reliability_band(
        success_rate=success_rate,
        failure_count=failure_count,
        average_fetched=average_fetched,
        utilization_rate=utilization["combined_hit_rate"],
    )

    return {
        "adapter": adapter,
        "reliability_band": band,
        "reliability_score": score,
        "run_count": run_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": success_rate,
        "latest_status": rollup["latest_status"],
        "last_error": rollup["last_error"] or None,
        "average_fetched_signals": average_fetched,
        "average_duration_ms": average_duration_ms,
        "utilization": utilization,
        "recommendations": _adapter_recommendations(
            adapter,
            band=band,
            failure_count=failure_count,
            success_rate=success_rate,
            average_fetched=average_fetched,
            utilization=utilization,
            last_error=rollup["last_error"],
        ),
    }


def _utilization_stats(quality: Mapping[str, Any] | None) -> dict[str, Any]:
    total_signals = _nonnegative_int((quality or {}).get("total_signals"))
    insight_hit_rate = _rate((quality or {}).get("insight_hit_rate"))
    idea_hit_rate = _rate((quality or {}).get("idea_hit_rate"))
    combined_hit_rate = round(max(insight_hit_rate, idea_hit_rate), 3)
    return {
        "available": quality is not None,
        "total_signals": total_signals,
        "insight_hit_rate": insight_hit_rate,
        "idea_hit_rate": idea_hit_rate,
        "combined_hit_rate": combined_hit_rate,
    }


def _reliability_score(
    *,
    success_rate: float,
    average_fetched: float,
    utilization_rate: float,
) -> float:
    yield_score = min(average_fetched / 5.0, 1.0)
    return round((success_rate * 0.55) + (yield_score * 0.25) + (utilization_rate * 0.20), 3)


def _reliability_band(
    *,
    success_rate: float,
    failure_count: int,
    average_fetched: float,
    utilization_rate: float,
) -> str:
    if failure_count > 0 and success_rate < 0.5:
        return "failing"
    if average_fetched < 1.0 or utilization_rate < 0.1:
        return "low_yield"
    if success_rate < 0.8 or average_fetched < 3.0 or utilization_rate < 0.25:
        return "watch"
    return "healthy"


def _adapter_recommendations(
    adapter: str,
    *,
    band: str,
    failure_count: int,
    success_rate: float,
    average_fetched: float,
    utilization: dict[str, Any],
    last_error: str,
) -> list[str]:
    recommendations: list[str] = []
    if band == "failing":
        error_hint = f" Last error: {last_error}." if last_error else ""
        recommendations.append(
            f"Repair `{adapter}` before increasing allocation; latest runs are failing.{error_hint}"
        )
    if failure_count and band != "failing":
        recommendations.append(
            f"Inspect intermittent `{adapter}` failures and add retry or quota handling."
        )
    if average_fetched < 1.0:
        recommendations.append(
            f"Lower `{adapter}` allocation or update query parameters because recent runs fetch few signals."
        )
    if utilization["available"] and utilization["total_signals"] > 0 and utilization["combined_hit_rate"] < 0.1:
        recommendations.append(
            f"Review `{adapter}` signal quality; persisted signals are rarely used by insights or ideas."
        )
    if not utilization["available"]:
        recommendations.append(
            f"Collect and synthesize `{adapter}` signals so utilization rates can be measured."
        )
    if not recommendations and success_rate >= 0.8:
        recommendations.append(f"Keep `{adapter}` enabled at current allocation and monitor drift.")
    return recommendations


def _report_next_actions(
    rows: list[dict[str, Any]],
    *,
    runs: list[dict[str, Any]],
    quality_stats: Mapping[str, Any],
) -> list[str]:
    if not runs and not quality_stats:
        return [
            "Run the pipeline with adapter metrics enabled, then synthesize signals to populate utilization stats."
        ]
    if not rows:
        return [
            "Lower min_runs or collect more pipeline runs before ranking adapter reliability."
        ]

    actions: list[str] = []
    failing = [row["adapter"] for row in rows if row["reliability_band"] == "failing"]
    low_yield = [row["adapter"] for row in rows if row["reliability_band"] == "low_yield"]
    watch = [row["adapter"] for row in rows if row["reliability_band"] == "watch"]
    if failing:
        actions.append(f"Repair failing adapters first: {', '.join(failing)}.")
    if low_yield:
        actions.append(f"Reduce allocation or retune low-yield adapters: {', '.join(low_yield)}.")
    if watch:
        actions.append(f"Monitor watch-list adapters for retry, quota, or relevance drift: {', '.join(watch)}.")
    if not actions:
        actions.append("Keep current adapter allocation and revisit after the next pipeline run.")
    return actions


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float):
        return max(0, int(value))
    return 0


def _rate(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if not isinstance(value, int | float):
        return 0.0
    return round(min(max(float(value), 0.0), 1.0), 3)
